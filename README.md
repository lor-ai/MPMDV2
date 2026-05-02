# Monoprice Mini Delta V2 (MPMDv2) — printer setup, firmware, and tooling

Working notes and recovery files for the MPMDv2 (`192.168.1.230`).
Goal: native OrcaSlicer integration as a 24/7 production printer alongside
the Bambu A1.

---

## TL;DR — current state

- **Motor firmware:** v1.2.0 (flashed via WEEDOIAP.exe over USB on Windows)
- **LCD firmware:** v1.5.0 (flashed via SD card → `Setting → IAP → LCD FW`)
- **Result:** printer's `/api/version` reports an OctoPrint-compatible string
  → OrcaSlicer's Octo/Klipper Host Type passes the Test button → native
  upload + monitoring work.
- **Network:** `http://192.168.1.230` (port 80). API key is **not validated**;
  send any non-empty value (e.g. `0`).
- **SD card:** 8GB FAT32, MBR partition table, single primary FAT32 partition.
  The printer enumerates SD only at **boot** — hot-swap is not supported.

---

## Why this folder exists

The original Monoprice firmware files (`flash.wfm` v1.2.0 motor + `lcd.efm`
v1.5.0 LCD) are **no longer hosted by Monoprice or the official wiki**.
The community repo at https://github.com/weedo3d/MiniDeltaV2firmware has
a *community-rebuilt* `flash.wfm` v1.2.0, but it uses the `WFM2.0` container
format which the stock bootloader cannot parse — flashing it via the SD-card
IAP path produces an `Error: unable to read version info` message and is a
brick risk if forced.

The *original Monoprice-released* files are `WFM1.0` format and flash cleanly.
A surviving mirror exists on Dropbox via reddit user sgallagh:
https://www.reddit.com/r/mpminidelta/comments/wfgajm/mpmdv2_firmware_update/

`firmware_originals/` in this folder is a local backup of that mirror.

---

## Files

```
firmware_originals/
  flash.wfm                              # Motor firmware v1.2.0 (WFM1.0 format)
  lcd.efm                                # LCD firmware v1.5.0 (WFM1.0 format) — THE OCTOPRINT-COMPAT ONE
  update.LCD                             # Older-style LCD update file (legacy bootloaders)
  MonopriceMiniDeltaV2FirmwareFiles.zip  # Original archive as downloaded
mpmdv2-upload.py                         # Pre-octoprint-fix workflow script (kept as fallback)
MPMDv2_FIRMWARE/                         # Community repo source code (reference only)
```

### Checksums (verify before flashing)

```
8744c638169910cdc18e293ae87474e2  flash.wfm
f6ea34fc6e5d731c93e28b93284be92b  lcd.efm
fd94105efbbf73221e2022cd32542734  update.LCD
197bcd0b46ff88ec9a8dcd852ed692c2  MonopriceMiniDeltaV2FirmwareFiles.zip
```

---

## How the printer was updated (recipe for next time)

### Step 1 — Motor firmware to v1.2.0 (USB, Windows)

Boot Windows. Install CH341 USB-serial driver (`CH341SER.ZIP` from Weedo repo's
`buildroot/driver/`). Run `WEEDOIAP.exe`, select COM port, open
`flash.wfm` (or the equivalent `.bin` from the community repo — WEEDOIAP
flashes raw binary), click Update. ~30s. Printer reboots automatically.

You can skip this step entirely if doing **only** the LCD update — sgallagh
on reddit reported that v1.5.0 LCD pulls the matching motor firmware
automatically over wifi after install. Untested locally.

### Step 2 — LCD firmware to v1.5.0 (SD card, Linux is fine)

1. Format SD card as FAT32 / MBR / single partition. **8 GB recommended.**
   ```
   sudo wipefs -a /dev/sdX
   sudo parted /dev/sdX --script mklabel msdos mkpart primary fat32 1MiB 100% set 1 lba on
   sudo mkfs.vfat -F 32 -n MPMDV2 /dev/sdX1
   ```
2. Copy `firmware_originals/lcd.efm` to the **root** of the SD card. Filename
   must be exactly `lcd.efm`. Optionally copy `flash.wfm` alongside it as
   `flash.wfm` if doing both.
3. `sync && sudo umount /dev/sdX1`. Pull card, insert in printer.
4. **Power-cycle the printer** (it only enumerates SD at boot).
5. From LCD: `Setting → IAP → LCD FW`. ~2 minutes. Brief "Error" message
   near the start is normal — let it run. Printer asks for power-cycle
   when done.
6. Reboot, confirm `LCD FW = 1.5.0` in the printer info screen.

### Step 3 — Verify OctoPrint compatibility

After v1.5.0 LCD is installed:

```bash
curl -s http://192.168.1.230/api/version
```

Should now report something starting with `OctoPrint` in the `text` field
(was `MiniDeltaLCD` on v1.4.2). This is the string OrcaSlicer's
`OctoPrint::validate_version_text` checks against and the entire reason
the firmware update was needed.

---

## OrcaSlicer setup (post-firmware)

In **Physical Printer**:

| Field           | Value                                  |
|-----------------|----------------------------------------|
| Host Type       | **Octo/Klipper**                       |
| Hostname/IP     | `http://192.168.1.230`                 |
| API Key         | `0` (any non-empty value works)        |
| HTTPS revoke    | leave unchecked                        |

Hit **Test** — should report success. Upload + auto-start now work natively
through the slicer's UI. The post-processing script approach is no longer
needed.

If the Test button still fails after v1.5.0 LCD flash, fall back to
`mpmdv2-upload.py` as a Process → Others → Post-processing script.

---

## API quick reference (what we found by direct probing)

- **`GET /api/version`** — version string. Used by Octo-compatible slicers
  for handshake. v1.4.2 returned `text:"MiniDeltaLCD"`. v1.5.0 reports
  OctoPrint-compatible.
- **`GET /api/printer`** — temps, state flags, `sd.ready`. `total: 0` here
  means SD card not seated/detected — power-cycle to re-enumerate.
- **`GET /api/files/local`** — list files on SD. Also has the `total`/`free`
  byte counts (only nonzero when SD is detected).
- **`POST /api/files/local`** — multipart upload. **MPMDv2 form fields:**
  `file=@<gcode>`, `select=true`, `print=true|false`. Does NOT take real
  OctoPrint's `path=` field — sends 500 if you include it.
- **`DELETE /api/files/local/<name>`** — delete a file. Works.
- **`POST /api/files/local/<name>` with `{"command":"select"}`** — accepts
  but silently no-ops on v1.4.2. Untested on v1.5.0.
- **`POST /api/job` with `{"command":"start"}`** — accepts but silently
  no-ops on v1.4.2. Untested on v1.5.0.
- **No API key validation** — header must be present (`X-Api-Key: <anything>`)
  but the value is not checked.
- **API self-identifies as Weedo** — `/api/printerprofiles` returns
  `"resource":"http://www.weedo.ltd"`. The MPMDv2 is a rebadged Weedo unit;
  the LCD/wifi is an ESP32-WROOM-32E with 4MB flash.

---

## Gotchas worth not forgetting

- **SD enumeration is boot-only.** Inserting an SD card on a running printer
  will not be detected. Always power-cycle after card swaps.
- **The HTTP upload response sometimes hangs forever** even though the file
  has already landed on the SD card. The `mpmdv2-upload.py` fallback works
  around this by polling `/api/files/local` for the filename to appear and
  exiting as soon as it does, instead of waiting on the (sometimes-stuck)
  POST response.
- **WFM container format matters.** `WFM1.0` headers (original Monoprice
  releases, in this folder) flash cleanly via SD. `WFM2.0` headers
  (community-built v1.2.0 in the GitHub repo) trigger
  `Error: unable to read version info` from the bootloader.
- **Brick risk.** A failed firmware flash can leave the printer stuck at
  the Monoprice logo on boot. Recovery requires WEEDOIAP.exe + Windows +
  USB cable. The community repo's `*_Community_to_Official.bin` is
  the recovery file. See https://github.com/piberry/-MPMDv2-modifications-and-fixes
  for ESP32-level reflashing if both motor and LCD bricks happen.
- **Refurbs ship without SD card or build plate.** Bring your own.

---

## Sources

- Reddit thread (sgallagh's mirror, working procedure):
  https://www.reddit.com/r/mpminidelta/comments/wfgajm/mpmdv2_firmware_update/
- Dropbox mirror (sgallagh):
  https://www.dropbox.com/scl/fi/puv3chgfzmx7w3apppdco/MonopriceMiniDeltaV2FirmwareFiles.zip
- Community firmware repo (motor source + community v1.2.0 builds):
  https://github.com/weedo3d/MiniDeltaV2firmware
- piberry's recovery + ESP32 dumps (last-resort unbricking):
  https://github.com/piberry/-MPMDv2-modifications-and-fixes
- jaredharley gist (early API reverse-engineering, traffic captures):
  https://gist.github.com/jaredharley/31e6a05da2a2edf44c5150d839439c9b
- Monoprice official manual (P/N 21666):
  https://downloads.monoprice.com/files/manuals/21666_Manual_210224.pdf
- OctoPrint API spec (the protocol the LCD firmware claims to implement):
  https://docs.octoprint.org/en/main/api/version.html

---

*Last updated: 2026-05-02. Printer firmware: motor 1.2.0, LCD 1.5.0.*
