"""Checks for the pure-logic helpers. Run: uv run python tests/test_logic.py (or pytest)."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from stock_screening import config, inventory, metrics, review, selection, sheets


def test_ids_roundtrip():
    assert review.parse_ids("1-4, 9,12") == [1, 2, 3, 4, 9, 12]
    assert review.compress_ids([12, 1, 2, 3, 4, 9, 3]) == "1-4,9,12"
    for bad in ("abc", "1-x", "5-3"):
        try:
            review.parse_ids(bad)
        except ValueError:
            continue
        raise AssertionError(f"parse_ids accepted {bad!r}")


def test_stem_grouping():
    data = config._read_toml(config.DEFAULT_CONFIG)
    norm = inventory.StemNormalizer(config.Config(Path("."), Path("."), data))
    d = "2020/2020-01-01"
    assert norm.split(f"{d}/DSC0001.ARW") == (f"{d}/dsc0001", False, False)
    assert norm.split(f"{d}/LRG_DSC0001.JPG") == (f"{d}/dsc0001", True, False)
    assert norm.split(f"{d}/DSC0001-Enhanced-NR-Edit.dng") == (f"{d}/dsc0001", False, True)
    assert norm.split(f"{d}/DSC0001-強化-NR.dng") == (f"{d}/dsc0001", False, True)


def test_capture_date():
    mtime = datetime(2021, 6, 1, 12, 0).timestamp()
    with tempfile.TemporaryDirectory() as tmp:
        with_exif, without_exif = Path(tmp, "a.jpg"), Path(tmp, "b.jpg")
        exif = Image.Exif()
        exif.get_ifd(0x8769)[0x9003] = "2019:05:01 10:00:00"  # DateTimeOriginal
        Image.new("RGB", (8, 8)).save(with_exif, exif=exif)
        Image.new("RGB", (8, 8)).save(without_exif)
        for p in (with_exif, without_exif):
            os.utime(p, (mtime, mtime))
        rec = metrics.capture_date(str(with_exif), mtime)
        assert (rec["captured_at"], rec["date_source"]) == ("2019-05-01T10:00:00", "exif")
        rec = metrics.capture_date(str(without_exif), mtime)
        assert (rec["captured_at"], rec["date_source"]) == ("2021-06-01T12:00:00", "mtime")


def test_exclude_globs():
    globs = ["*.lrdata", "Exports", "*/Edited/*"]
    assert inventory.is_excluded("Lightroom/Previews.lrdata/a/b.jpg", globs)
    assert inventory.is_excluded("Exports/x.jpg", globs)
    assert inventory.is_excluded("Trip/Edited/x.jpg", globs)
    assert inventory.is_excluded("Trip/.thumbs/x.jpg", [])       # hidden folder
    assert inventory.is_excluded(".DS_Store", [])                 # hidden file
    assert not inventory.is_excluded("Trip/Exports2/x.jpg", globs)
    assert not inventory.is_excluded("Camera/IMG_0001.jpg", globs)


def test_sheets_resume():
    with tempfile.TemporaryDirectory() as tmp:
        photos, out = Path(tmp, "photos"), Path(tmp, "out")
        photos.mkdir()
        data = config._read_toml(config.DEFAULT_CONFIG)
        data["sheets"].update(columns=1, rows=1, tile_px=64)  # one tile per sheet
        cfg = config.Config(photos, out, data)
        with open(cfg.year_dir("2020") / selection.SCREEN_NAME, "w", encoding="utf-8") as fh:
            fh.write("relpath,status,kind,captured_at\n")
            for i in range(3):
                Image.new("RGB", (8, 8)).save(photos / f"{i}.jpg")
                fh.write(f"{i}.jpg,pass,jpeg,2020-01-0{i + 1}T00:00:00\n")
        out_sheets = sheets.sheets_dir(cfg, "2020")

        assert sheets.run(cfg, "2020", time_budget=1e-9, workers=1) == 3  # budget hit at once
        assert sheets.rendered(cfg, "2020") == set()
        assert sheets.run(cfg, "2020", workers=1) == 0
        assert sheets.rendered(cfg, "2020") == {"sheet_001.jpg", "sheet_002.jpg", "sheet_003.jpg"}

        # Same index: only sheets missing from rendered.txt are drawn again.
        (out_sheets / "rendered.txt").write_text("sheet_001.jpg\nsheet_003.jpg\n")
        for name in ("sheet_001.jpg", "sheet_002.jpg"):
            os.utime(out_sheets / name, (0, 0))
        assert sheets.run(cfg, "2020", workers=1) == 0
        assert (out_sheets / "sheet_001.jpg").stat().st_mtime == 0
        assert (out_sheets / "sheet_002.jpg").stat().st_mtime > 0

        # A decision changes the index: everything is re-rendered, stale sheet removed.
        review.mark(cfg, "2020", "1", "reject", [], "")
        os.utime(out_sheets / "sheet_001.jpg", (0, 0))
        assert sheets.run(cfg, "2020", workers=1) == 0
        assert (out_sheets / "sheet_001.jpg").stat().st_mtime > 0
        assert sorted(sheets.read_index(cfg, "2020")) == ["0001", "0002"]
        assert not (out_sheets / "sheet_003.jpg").exists()


if __name__ == "__main__":
    test_ids_roundtrip()
    test_stem_grouping()
    test_capture_date()
    test_exclude_globs()
    test_sheets_resume()
    print("ok")
