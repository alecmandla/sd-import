# mac-sd-photo-import

Plug in your SD card. Photos auto-organize into `~/Pictures/YYYY/MM-Month/`. Card ejects. Done.

## Why

If importing photos takes more than zero clicks, the SD card stays in the camera and the photos never get seen. This tool removes the friction: the moment macOS mounts the card, a `launchd` agent fires, the files are sorted by EXIF date into year/month folders, and the card ejects on its own. The next time you sit down at your Mac the photos are already there.

## Install

Requires macOS and Python 3.9+ (the system `python3` from the Xcode Command Line Tools works).

```bash
git clone https://github.com/alecmandla/sd-import.git
cd sd-import
./install.sh
```

That's it. The installer:

- Installs `Pillow` and `exifread` via `pip --user`
- Copies the script to `~/.local/bin/sd-import`
- Drops a starter config at `~/.config/sd-photo-import/config.toml`
- Loads a `launchd` agent at `~/Library/LaunchAgents/com.user.sdimport.plist`

## What it does

- Watches `/Volumes` via `launchd`. When any volume mounts, it checks for a `DCIM/` folder (the standard camera SD card marker). Volumes without `DCIM/` are silently ignored.
- Reads EXIF `DateTimeOriginal` for each photo (Pillow → exifread → file mtime fallback).
- Moves photos into `<destination>/YYYY/MM-Month/`.
- RAW files (`.cr3`, `.nef`, `.arw`, etc.) go into a `RAW/` subfolder inside the month.
- If a file with the same name and size already exists at the destination, it's treated as already imported and removed from the card. Different file, same name → counter appended to disambiguate.
- Optional **copy mode** (`mode = "copy"`) leaves photos on the card and keeps a small ledger so the same photos aren't imported twice.
- Optional **fallback destination**: if the destination is on an external drive that isn't plugged in, photos are staged in the fallback folder and moved to the drive automatically the next time it mounts (or left in place with `drain_fallback = false`, if you'd rather move them yourself).
- Ejects the card when done.
- Pops a macOS notification when starting and finishing.

## First-time use

After install, insert an SD card and run a dry-run from the terminal first so you can see what it would do:

```bash
sd-import --dry-run
tail -f ~/Library/Logs/sd-import.log
```

If it looks right, eject the card and re-insert it. `launchd` will fire the real import this time.

## Configuration

Edit `~/.config/sd-photo-import/config.toml`. See [config.example.toml](config.example.toml) for the full set of options and defaults.

```toml
[paths]
destination = "~/Pictures"
fallback_destination = ""         # e.g. "~/Pictures/inbox" when destination is an external drive
ledger = "~/.local/state/sd-import/imported.tsv"

[behavior]
mode = "move"                     # or "copy" to leave photos on the card
eject_when_done = true
month_folder_format = "{month_num:02d}-{month_name}"   # -> "05-May"
raw_subfolder = "RAW"

[filetypes]
jpeg  = [".jpg", ".jpeg"]
raw   = [".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf", ".dng", ".pef", ".srw"]
video = [".mp4", ".mov", ".avi", ".m4v"]
```

**Tip:** pointing `destination` at a cloud-synced folder (Google Drive, iCloud Drive, Dropbox) gives you automatic offsite backup of every import.

Available `month_folder_format` placeholders: `{month_num}`, `{month_num:02d}`, `{month_name}`, `{year}`.

## CLI flags

```
sd-import --dry-run        # log what would happen, don't move or eject
sd-import --config PATH    # use a non-default config file
sd-import --version
```

## Logs

- `~/Library/Logs/sd-import.log` — what the script did
- `~/Library/Logs/sd-import.stdout.log` / `sd-import.stderr.log` — anything `launchd` captured

## Troubleshooting

### "Operation not permitted" or imports landing in the fallback folder

macOS privacy controls (TCC) treat SD cards and external drives as *removable volumes*. A `launchd` job never gets the permission prompt an app would, so the first time the script touches a removable volume from the background, macOS can silently deny it. You'll see `PermissionError: [Errno 1] Operation not permitted` in `~/Library/Logs/sd-import.stderr.log`, or with a `fallback_destination` set, a notification that access was blocked and the photos went to the fallback folder instead.

Running `sd-import` from Terminal works because Terminal has its own permission. To fix the background job:

1. Find the Python the agent actually runs. `/usr/bin/python3` is a shim; the real interpreter lives inside the Command Line Tools or Xcode:
   ```bash
   /usr/bin/python3 -c 'import sys; print(sys.executable)'
   ```
2. In **System Settings → Privacy & Security → Full Disk Access**, click **+**, press **⌘⇧G**, and add that path.

That grants the access to every script run by that Python. If you'd rather not, run the script through a small app bundle that launches only `sd_import.py`, and grant access to that app instead.

Switching between Xcode and the Command Line Tools (`xcode-select`) changes which interpreter runs, so a grant that worked before can stop working.

## Turning it off / back on

```bash
launchctl unload ~/Library/LaunchAgents/com.user.sdimport.plist
launchctl load   ~/Library/LaunchAgents/com.user.sdimport.plist
```

## Uninstall

```bash
./uninstall.sh
```

Removes the script and the `launchd` agent. Config and logs are left in place; the script prints their paths so you can delete them manually if you want.

## How it works under the hood

The `launchd` agent uses `WatchPaths` on `/Volumes`, which fires whenever any drive mounts or unmounts — SD card, USB stick, external drive, anything. The script wakes up, scans `/Volumes` for anything with a `DCIM/` folder, and only acts on those. A 10-second `ThrottleInterval` keeps it from re-firing while a previous import is still running.

This is macOS-specific by design — `WatchPaths` and `diskutil eject` don't exist on Linux or Windows. The repo name reflects that.

## Contributing

Issues and PRs welcome. Run the tests with:

```bash
uv run --no-project --python 3.9 --with pytest --with Pillow --with exifread --with tomli -- pytest tests
```

(or `pip install -e '.[test]' && pytest`). The tests build small JPEGs with EXIF dates on the fly and use a fake card; they never touch `/Volumes` or eject anything.

Known limitations:

- macOS only.
- EXIF date extraction relies on `DateTimeOriginal`; videos with no EXIF date fall back to file mtime, which is usually correct but not guaranteed.

## License

MIT — see [LICENSE](LICENSE).
