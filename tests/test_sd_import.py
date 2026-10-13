from datetime import datetime
from pathlib import Path

import pytest

from conftest import make_jpeg


def config(sd, dest, *, mode="move", fallback="", ledger=""):
    cfg = sd.load_config(Path("/nonexistent/config.toml"))
    cfg["paths"].update(destination=str(dest), fallback_destination=str(fallback),
                        ledger=str(ledger))
    cfg["behavior"]["mode"] = mode
    return cfg


def run(sd, monkeypatch, cfg, cards):
    monkeypatch.setattr(sd, "load_config", lambda path: cfg)
    monkeypatch.setattr(sd, "find_sd_cards", lambda: list(cards))
    return sd.main([])


def files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


# --- date and path helpers -------------------------------------------------

def test_reads_exif_capture_date(sd, card):
    taken = sd.get_photo_datetime(card / "DCIM" / "100_FUJI" / "DSCF0001.JPG")
    assert taken == datetime(2026, 5, 10, 13, 17, 27)


def test_raw_files_go_to_raw_subfolder(sd, tmp_path):
    cfg = config(sd, tmp_path)
    taken = datetime(2026, 10, 3)
    assert sd.destination_for(Path("DSCF1.RAF"), taken, cfg, tmp_path) == \
        tmp_path / "2026" / "10-October" / "RAW" / "DSCF1.RAF"
    assert sd.destination_for(Path("DSCF1.JPG"), taken, cfg, tmp_path) == \
        tmp_path / "2026" / "10-October" / "DSCF1.JPG"


# --- move mode (the default) ------------------------------------------------

def test_move_mode_empties_card_and_ejects(sd, monkeypatch, tmp_path, card):
    dest = tmp_path / "Pictures"
    dest.mkdir()
    assert run(sd, monkeypatch, config(sd, dest), [card]) == 0
    assert files(dest) == ["2025/02-February/DSCF0002.JPG", "2026/05-May/DSCF0001.JPG"]
    assert files(card) == []
    assert sd.ejected == ["CARD"]


def test_missing_destination_without_fallback_fails(sd, monkeypatch, tmp_path, card):
    assert run(sd, monkeypatch, config(sd, tmp_path / "nope"), [card]) == 1
    assert len(files(card)) == 2


# --- copy mode + ledger -------------------------------------------------------

def test_copy_mode_leaves_photos_on_card(sd, monkeypatch, tmp_path, card):
    dest = tmp_path / "Pictures"
    dest.mkdir()
    cfg = config(sd, dest, mode="copy", ledger=tmp_path / "ledger.tsv")
    assert run(sd, monkeypatch, cfg, [card]) == 0
    assert len(files(dest)) == 2
    assert len(files(card)) == 2
    assert sd.ejected == ["CARD"]


def test_copy_mode_skips_photos_already_imported(sd, monkeypatch, tmp_path, card):
    dest = tmp_path / "Pictures"
    dest.mkdir()
    cfg = config(sd, dest, mode="copy", ledger=tmp_path / "ledger.tsv")
    run(sd, monkeypatch, cfg, [card])
    for f in dest.rglob("*.JPG"):
        f.unlink()  # e.g. moved elsewhere since the first import
    sd.ejected.clear()

    run(sd, monkeypatch, cfg, [card])
    assert files(dest) == []  # ledger stopped a re-import
    assert sd.ejected == []  # nothing new, so the card stays mounted

    make_jpeg(card / "DCIM" / "100_FUJI" / "DSCF0003.JPG", datetime(2026, 5, 11, 8, 0, 0))
    run(sd, monkeypatch, cfg, [card])
    assert files(dest) == ["2026/05-May/DSCF0003.JPG"]


def test_copy_mode_same_name_different_photo_gets_counter(sd, monkeypatch, tmp_path, card):
    dest = tmp_path / "Pictures"
    existing = make_jpeg(dest / "2026" / "05-May" / "DSCF0001.JPG",
                         datetime(2026, 5, 10, 13, 17, 27), color=(1, 2, 3))
    existing.write_bytes(existing.read_bytes() + b"different")
    cfg = config(sd, dest, mode="copy", ledger=tmp_path / "ledger.tsv")
    run(sd, monkeypatch, cfg, [card])
    assert "2026/05-May/DSCF0001_1.JPG" in files(dest)


# --- fallback destination ----------------------------------------------------

def test_unmounted_destination_uses_fallback_then_drains(sd, monkeypatch, tmp_path, card):
    drive = tmp_path / "Volumes" / "Archive"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = config(sd, drive, mode="copy", fallback=inbox, ledger=tmp_path / "ledger.tsv")

    assert run(sd, monkeypatch, cfg, [card]) == 0
    assert files(inbox) == ["2025/02-February/DSCF0002.JPG", "2026/05-May/DSCF0001.JPG"]

    drive.mkdir(parents=True)  # the drive is plugged in; no card this time
    assert run(sd, monkeypatch, cfg, []) == 0
    assert files(drive) == ["2025/02-February/DSCF0002.JPG", "2026/05-May/DSCF0001.JPG"]
    assert files(inbox) == []
    assert inbox.is_dir()  # the fallback folder itself is kept


def test_drain_drops_duplicates_already_on_destination(sd, monkeypatch, tmp_path, card):
    drive = tmp_path / "Archive"
    inbox = tmp_path / "inbox"
    src = card / "DCIM" / "100_FUJI" / "DSCF0001.JPG"
    for root in (drive, inbox):
        target = root / "2026" / "05-May" / "DSCF0001.JPG"
        target.parent.mkdir(parents=True)
        target.write_bytes(src.read_bytes())
    run(sd, monkeypatch, config(sd, drive, fallback=inbox), [])
    assert files(drive) == ["2026/05-May/DSCF0001.JPG"]
    assert files(inbox) == []


def test_permission_denied_destination_uses_fallback(sd, monkeypatch, tmp_path, card):
    # macOS privacy controls can stop a launchd job from listing an external
    # drive. That should fall back, not crash.
    drive = tmp_path / "Archive"
    drive.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == drive:
            raise PermissionError(1, "Operation not permitted", str(self))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    cfg = config(sd, drive, mode="copy", fallback=inbox, ledger=tmp_path / "ledger.tsv")
    assert run(sd, monkeypatch, cfg, [card]) == 0
    assert len(files(inbox)) == 2
    assert any("blocked access" in n for n in sd.notes)


def test_permission_denied_without_card_stays_quiet(sd, monkeypatch, tmp_path):
    # Every mount (USB sticks, other drives) wakes the job; with no card
    # waiting there is nothing to tell the user.
    drive = tmp_path / "Archive"
    drive.mkdir()
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == drive:
            raise PermissionError(1, "Operation not permitted", str(self))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    assert run(sd, monkeypatch, config(sd, drive), []) == 1
    assert sd.notes == []


@pytest.mark.parametrize("mode", ["move", "copy"])
def test_dry_run_changes_nothing(sd, monkeypatch, tmp_path, card, mode):
    dest = tmp_path / "Pictures"
    dest.mkdir()
    cfg = config(sd, dest, mode=mode, ledger=tmp_path / "ledger.tsv")
    monkeypatch.setattr(sd, "load_config", lambda path: cfg)
    monkeypatch.setattr(sd, "find_sd_cards", lambda: [card])
    assert sd.main(["--dry-run"]) == 0
    assert files(dest) == []
    assert len(files(card)) == 2
    assert not (tmp_path / "ledger.tsv").exists()
