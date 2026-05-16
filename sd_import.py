#!/usr/bin/env python3
"""
SD Card Photo Importer (macOS)

Watches for SD card mounts via launchd, finds photos in DCIM/, reads each
photo's EXIF DateTimeOriginal, and moves files into
<destination>/YYYY/<month_folder>/. RAW files go into a RAW/ subfolder.
Ejects the card when finished. Logs to ~/Library/Logs/sd-import.log.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

__version__ = "0.1.0"

HOME = Path.home()
LOG_FILE = HOME / "Library" / "Logs" / "sd-import.log"
VOLUMES_DIR = Path("/Volumes")
DEFAULT_CONFIG_PATH = HOME / ".config" / "sd-photo-import" / "config.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {"destination": "~/Pictures"},
    "behavior": {
        "eject_when_done": True,
        "month_folder_format": "{month_num:02d}-{month_name}",
        "raw_subfolder": "RAW",
    },
    "filetypes": {
        "jpeg": [".jpg", ".jpeg"],
        "raw": [".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf",
                ".dng", ".pef", ".srw"],
        "video": [".mp4", ".mov", ".avi", ".m4v"],
    },
}

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sd-import")


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config(path: Path | None) -> dict[str, Any]:
    """Load TOML config, merging over the defaults. Missing file is fine."""
    cfg = {section: dict(values) for section, values in DEFAULT_CONFIG.items()}
    target = path or DEFAULT_CONFIG_PATH
    if not target.exists():
        log.info(f"No config at {target}, using defaults")
        return cfg
    try:
        user = _load_toml(target)
    except Exception as e:
        log.error(f"Failed to read config {target}: {e}. Using defaults.")
        return cfg
    for section, values in user.items():
        if isinstance(values, dict) and section in cfg:
            cfg[section].update(values)
        else:
            cfg[section] = values
    log.info(f"Loaded config from {target}")
    return cfg


def notify(title: str, message: str) -> None:
    """Send a macOS notification via osascript."""
    safe_msg = message.replace('"', "'")
    safe_title = title.replace('"', "'")
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_msg}" with title "{safe_title}"'],
            check=False,
            timeout=5,
        )
    except Exception as e:
        log.warning(f"Notification failed: {e}")


def get_photo_datetime(path: Path) -> datetime:
    """
    Return when the photo/video was taken. Tries EXIF DateTimeOriginal via
    Pillow, then exifread, then falls back to file mtime.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(path) as img:
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    if TAGS.get(tag_id) == "DateTimeOriginal" and value:
                        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    try:
        import exifread

        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False,
                                         stop_tag="DateTimeOriginal")
            if "EXIF DateTimeOriginal" in tags:
                return datetime.strptime(str(tags["EXIF DateTimeOriginal"]),
                                         "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    log.warning(f"No EXIF date for {path.name}, using file mtime")
    return datetime.fromtimestamp(path.stat().st_mtime)


def find_sd_cards() -> list[Path]:
    """Mounted volumes that look like camera SD cards (contain DCIM/)."""
    cards = []
    if not VOLUMES_DIR.exists():
        return cards
    for vol in VOLUMES_DIR.iterdir():
        if vol.name.startswith("."):
            continue
        if (vol / "DCIM").is_dir():
            cards.append(vol)
    return cards


def find_media_files(card_root: Path, all_exts: set[str]) -> list[Path]:
    """Recursively find photo/video files on the card."""
    files = []
    for path in (card_root / "DCIM").rglob("*"):
        if path.is_file() and path.suffix.lower() in all_exts:
            files.append(path)
    return files


def month_folder_name(taken: datetime, fmt: str) -> str:
    return fmt.format(
        month_num=taken.month,
        month_name=calendar.month_name[taken.month],
        year=taken.year,
    )


def destination_for(file: Path, taken: datetime, cfg: dict[str, Any],
                    dest_root: Path) -> Path:
    fmt = cfg["behavior"].get("month_folder_format",
                              DEFAULT_CONFIG["behavior"]["month_folder_format"])
    raw_sub = cfg["behavior"].get("raw_subfolder",
                                  DEFAULT_CONFIG["behavior"]["raw_subfolder"])
    raw_exts = {e.lower() for e in cfg["filetypes"]["raw"]}

    month_folder = dest_root / str(taken.year) / month_folder_name(taken, fmt)
    if file.suffix.lower() in raw_exts and raw_sub:
        return month_folder / raw_sub / file.name
    return month_folder / file.name


def safe_move(src: Path, dst: Path, dest_root: Path,
              dry_run: bool = False) -> bool:
    """
    Move src to dst, creating parents as needed. If dst exists and is the
    same size, treat as already imported and remove src instead. If sizes
    differ, append a counter to disambiguate. Returns True if the card got
    one file lighter.
    """
    if dry_run:
        log.info(f"[dry-run] Would move {src.name} -> "
                 f"{dst.relative_to(dest_root) if dest_root in dst.parents else dst}")
        return True

    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        if dst.stat().st_size == src.stat().st_size:
            log.info(f"Already imported: {src.name} (removing from card)")
            src.unlink()
            return True
        stem, suffix = dst.stem, dst.suffix
        counter = 1
        while dst.exists():
            dst = dst.with_name(f"{stem}_{counter}{suffix}")
            counter += 1

    shutil.move(str(src), str(dst))
    try:
        rel = dst.relative_to(dest_root)
    except ValueError:
        rel = dst
    log.info(f"Moved {src.name} -> {rel}")
    return True


def import_card(card: Path, cfg: dict[str, Any], dest_root: Path,
                dry_run: bool) -> tuple[int, int, int]:
    """Import all media from a card. Returns (moved, errors, total_found)."""
    exts = (set(e.lower() for e in cfg["filetypes"]["jpeg"]) |
            set(e.lower() for e in cfg["filetypes"]["raw"]) |
            set(e.lower() for e in cfg["filetypes"]["video"]))

    files = find_media_files(card, exts)
    if not files:
        log.info(f"No media files on {card.name}")
        return (0, 0, 0)

    log.info(f"Found {len(files)} media files on {card.name}")
    moved = 0
    errors = 0
    for f in files:
        try:
            taken = get_photo_datetime(f)
            dst = destination_for(f, taken, cfg, dest_root)
            if safe_move(f, dst, dest_root, dry_run=dry_run):
                moved += 1
        except Exception as e:
            log.error(f"Failed to import {f.name}: {e}")
            errors += 1
    return (moved, errors, len(files))


def eject_card(card: Path) -> bool:
    try:
        result = subprocess.run(
            ["diskutil", "eject", str(card)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log.info(f"Ejected {card.name}")
            return True
        log.error(f"Eject failed for {card.name}: {result.stderr.strip()}")
        return False
    except Exception as e:
        log.error(f"Eject error for {card.name}: {e}")
        return False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sd-import",
        description="Auto-import photos from an SD card on macOS.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Log intended moves without touching files or ejecting.")
    p.add_argument("--config", type=Path, default=None,
                   help=f"Path to config TOML (default: {DEFAULT_CONFIG_PATH}).")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log.info("=" * 60)
    log.info(f"SD import triggered (v{__version__}"
             f"{', dry-run' if args.dry_run else ''})")

    cfg = load_config(args.config)
    dest_root = Path(cfg["paths"]["destination"]).expanduser()

    if not dest_root.exists():
        log.error(f"Destination root does not exist: {dest_root}")
        notify("SD Import", f"Destination folder missing: {dest_root}")
        return 1

    cards = find_sd_cards()
    if not cards:
        log.info("No SD cards with DCIM/ found — nothing to do")
        return 0

    for card in cards:
        log.info(f"Processing {card}")
        notify("SD Import", f"Importing photos from {card.name}…")

        moved, errors, total = import_card(card, cfg, dest_root, args.dry_run)

        if args.dry_run:
            notify("SD Import",
                   f"[dry-run] Would import {moved} of {total} files from {card.name}.")
            continue

        if errors == 0 and moved > 0:
            if cfg["behavior"].get("eject_when_done", True):
                eject_card(card)
                notify("SD Import", f"Imported {moved} files. Card ejected.")
            else:
                notify("SD Import", f"Imported {moved} files.")
        elif moved > 0:
            notify("SD Import",
                   f"Imported {moved} of {total} files. {errors} errors. Check log.")
        else:
            notify("SD Import", f"No files imported from {card.name}")

    log.info("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
