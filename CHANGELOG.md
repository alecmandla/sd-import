# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Animated GIF demo in README
- Module split if `sd_import.py` outgrows a single file
- Linux/Windows ports (currently macOS-only via `launchd` and `diskutil`)

## [0.2.0] - 2026-10-13

### Added
- `behavior.mode = "copy"` leaves photos on the card instead of moving them.
  Each copy is size-checked before it counts.
- `paths.ledger`: in copy mode, a record of imported files so re-inserting a
  card doesn't re-import old photos.
- `paths.fallback_destination`: when the destination drive isn't mounted,
  photos are staged here and drained into the destination the next time it
  mounts (the launchd trigger already fires on every mount).
  `behavior.drain_fallback = false` turns the automatic drain off.
- Test suite (`tests/`, pytest) covering EXIF dates, destination paths, move
  and copy modes, the ledger, fallback and drain, and dry runs.
- README troubleshooting section for macOS privacy (TCC) denials when the job
  runs from launchd.

### Changed
- The card is only ejected when something new was imported.
- If macOS privacy controls block access to the destination (common for a
  launchd job writing to an external drive), the fallback folder is used and
  a notification explains why, instead of the import crashing.

## [0.1.0] - 2026-05-15

### Added
- Initial release.
- `sd_import.py` script: detects SD cards with a `DCIM/` folder under `/Volumes`,
  reads EXIF `DateTimeOriginal` (Pillow, then `exifread`, then file mtime as
  fallback), and moves photos and videos into `~/Pictures/YYYY/MM-Month/`. RAW
  files go into a `RAW/` subfolder. Card is ejected when done.
- Config file at `~/.config/sd-photo-import/config.toml` controls destination,
  eject behavior, month folder naming, and file-type extensions.
- `--dry-run`, `--config`, and `--version` CLI flags.
- `install.sh` / `uninstall.sh` for one-command setup and teardown.
- `launchd` agent template (`com.user.sdimport.plist.template`) watching
  `/Volumes` with a 10-second throttle.
- macOS notifications via `osascript` when importing starts and finishes.
- MIT license.
