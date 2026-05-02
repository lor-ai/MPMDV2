#!/usr/bin/env python3
"""
OrcaSlicer post-processing script: upload sliced gcode to MPMDv2 over wifi.

Quirk handled: the MPMDv2 firmware writes the file successfully but
sometimes never closes the HTTP response connection. So instead of waiting
on the response, we POST in a background thread and poll /api/files/local
for the filename. As soon as the file shows up on the SD card, we exit.

Usage (OrcaSlicer fills argv[1] automatically):
  mpmdv2-upload.py /path/to/sliced.gcode

Toggle START_PRINT below if you want auto-start on upload.
"""
import sys, os, time, threading, traceback, json, mimetypes, uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PRINTER         = "http://192.168.1.230"
API_KEY         = "0"           # any non-empty value works
START_PRINT     = False         # True to auto-start print after upload
LOG             = "/tmp/mpmdv2-upload.log"
POLL_INTERVAL   = 1.0           # seconds between SD-card polls
POLL_TIMEOUT    = 180           # max seconds to wait for file to appear
POST_TIMEOUT    = 600           # POST socket timeout (large gcode tolerance)

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, file=sys.stderr)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def build_multipart(fields, file_field, file_path):
    boundary = f"----OrcaMPMDv2{uuid.uuid4().hex}"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(value.encode() + b"\r\n")
    fname = os.path.basename(file_path)
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="{file_field}"; filename="{fname}"\r\n'.encode())
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode())
    with open(file_path, "rb") as f:
        parts.append(f.read())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"

def upload_in_background(body, content_type, result_holder):
    req = Request(
        f"{PRINTER}/api/files/local",
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "X-Api-Key": API_KEY,
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urlopen(req, timeout=POST_TIMEOUT) as resp:
            result_holder["status"] = resp.status
            result_holder["body"] = resp.read()[:200]
    except HTTPError as e:
        result_holder["status"] = e.code
        try: result_holder["body"] = e.read()[:200]
        except: pass
    except (URLError, OSError) as e:
        result_holder["error"] = str(e)
    except Exception as e:
        result_holder["error"] = f"unexpected: {e}"

def poll_for_file(target_name, total_size, deadline):
    """Return True when the printer reports our file. False on timeout."""
    while time.time() < deadline:
        try:
            with urlopen(f"{PRINTER}/api/files/local", timeout=5) as r:
                data = json.loads(r.read())
            for f in data.get("files", []):
                if f.get("name") == target_name:
                    return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    return False

def main():
    if len(sys.argv) < 2:
        log("ERROR: no gcode path passed by OrcaSlicer")
        sys.exit(1)
    src = sys.argv[1]
    if not os.path.exists(src):
        log(f"ERROR: file not found: {src}")
        sys.exit(1)
    target_name = os.path.basename(src)
    size_mb = os.path.getsize(src) / 1024 / 1024
    log(f"Uploading {target_name} ({size_mb:.2f} MB)")

    fields = {
        "select": "true",
        "print":  "true" if START_PRINT else "false",
    }
    body, content_type = build_multipart(fields, "file", src)

    # Fire the POST in a background thread (it may hang waiting for response).
    result = {}
    t0 = time.time()
    poster = threading.Thread(target=upload_in_background,
                              args=(body, content_type, result),
                              daemon=True)
    poster.start()

    # Poll the printer for the file to appear on the SD card.
    deadline = time.time() + POLL_TIMEOUT
    if poll_for_file(target_name, len(body), deadline):
        elapsed = time.time() - t0
        log(f"OK: {target_name} confirmed on SD card in {elapsed:.1f}s")
        # Don't wait for the (possibly stuck) POST thread - it's a daemon,
        # so it dies when we exit.
        sys.exit(0)
    else:
        log(f"TIMEOUT: file did not appear on SD after {POLL_TIMEOUT}s")
        log(f"  background POST status: {result}")
        # Don't fail the slice — gcode file is still on local disk
        sys.exit(0)

if __name__ == "__main__":
    main()
