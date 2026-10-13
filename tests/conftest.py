import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# sd_import configures logging to ~/Library/Logs at import time. Point HOME at
# a scratch directory first so test runs never write to the real log.
os.environ["HOME"] = tempfile.mkdtemp(prefix="sd-import-test-home-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sd_import  # noqa: E402


@pytest.fixture
def sd(monkeypatch):
    """The sd_import module with macOS side effects stubbed out."""
    notes, ejected = [], []
    monkeypatch.setattr(sd_import, "notify", lambda title, msg: notes.append(msg))
    monkeypatch.setattr(sd_import, "eject_card",
                        lambda card: ejected.append(card.name) or True)
    sd_import.notes, sd_import.ejected = notes, ejected
    return sd_import


def make_jpeg(path: Path, taken: datetime, color=(200, 100, 50)) -> Path:
    """A small JPEG with EXIF DateTimeOriginal, like a camera writes."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (32, 24), color)
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = taken.strftime("%Y:%m:%d %H:%M:%S")
    img.save(path, "JPEG", exif=exif.tobytes())
    return path


@pytest.fixture
def card(tmp_path):
    """A fake SD card with two photos from different months."""
    root = tmp_path / "CARD"
    make_jpeg(root / "DCIM" / "100_FUJI" / "DSCF0001.JPG", datetime(2026, 5, 10, 13, 17, 27))
    make_jpeg(root / "DCIM" / "100_FUJI" / "DSCF0002.JPG", datetime(2025, 2, 1, 9, 0, 0),
              color=(10, 20, 30))
    return root
