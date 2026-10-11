"""Step 2a: render numbered contact sheets of the files that passed `select`.

Each tile shows a 4-digit ID and the capture time. <out>/<year>/sheets/index.csv maps
IDs to files; `mark` uses it to record review decisions.

Rendering is resumable like `scan`: index.csv is written first, rendered.txt lists the
sheets finished for it, and a re-run with the same index only renders the missing ones.
"""

from __future__ import annotations

import csv
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import metrics, review, selection
from .config import Config

INDEX_NAME = "index.csv"
INDEX_FIELDS = ["id", "sheet", "relpath", "captured_at"]
DONE_NAME = "rendered.txt"


def sheets_dir(cfg: Config, year: str) -> Path:
    path = cfg.year_dir(year) / "sheets"
    path.mkdir(exist_ok=True)
    return path


def read_index(cfg: Config, year: str) -> dict[str, dict[str, str]]:
    path = sheets_dir(cfg, year) / INDEX_NAME
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `sheets --year {year}` first")
    with open(path, newline="", encoding="utf-8") as fh:
        return {row["id"]: row for row in csv.DictReader(fh)}


def rendered(cfg: Config, year: str) -> set[str]:
    """Sheet files fully written for the current index.csv."""
    path = sheets_dir(cfg, year) / DONE_NAME
    return set(path.read_text(encoding="utf-8").split()) if path.exists() else set()


def _tile(path_str: str, kind: str, size: tuple[int, int]) -> Image.Image | None:
    """Preview scaled to fit one tile, or None if unreadable. Runs in a worker process."""
    try:
        img, _, _ = metrics.load_preview(Path(path_str), kind)
        img.thumbnail(size)
        return img
    except Exception:
        return None


def run(cfg: Config, year: str, include_reviewed: bool = False,
        time_budget: float = 0, workers: int = 0) -> int:
    deadline = time.monotonic() + time_budget if time_budget else None
    workers = workers or os.cpu_count() or 1
    opts = cfg.section("sheets")
    cols, rows_n, tile = opts["columns"], opts["rows"], opts["tile_px"]

    reviewed = set() if include_reviewed else set(review.load(cfg, year))
    passed = [r for r in selection.read_screen(cfg, year)
              if r["status"] == "pass" and r["relpath"] not in reviewed]
    passed.sort(key=lambda r: (r.get("captured_at") or "", r["relpath"]))
    out = sheets_dir(cfg, year)

    per_sheet = cols * rows_n
    index_rows = [{"id": f"{i + 1:04d}", "sheet": f"sheet_{i // per_sheet + 1:03d}.jpg",
                   "relpath": r["relpath"], "captured_at": r.get("captured_at") or ""}
                  for i, r in enumerate(passed)]
    try:
        resume = list(read_index(cfg, year).values()) == index_rows
    except FileNotFoundError:
        resume = False
    if resume:
        done = rendered(cfg, year)
    else:
        # Clear rendered.txt before replacing index.csv, so an interruption in between can
        # never mark old sheets as done for the new index. The (possibly empty) index is
        # always rewritten so `mark` cannot hit IDs from an earlier run.
        (out / DONE_NAME).write_text("", encoding="utf-8")
        with open(out / INDEX_NAME, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
            writer.writeheader()
            writer.writerows(index_rows)
        done = set()

    by_sheet: dict[str, list[dict[str, str]]] = {}
    for idx, row in zip(index_rows, passed):
        by_sheet.setdefault(idx["sheet"], []).append({**idx, "kind": row["kind"]})
    n_sheets = len(by_sheet)
    todo = [name for name in by_sheet if name not in done]
    if passed:
        print(f"[sheets {year}] {len(passed)} images on {n_sheets} sheets, "
              f"{len(todo)} to render", flush=True)

    label_h = max(28, tile // 16)
    box_h = int(tile * 0.8)
    cell_w, cell_h, pad = tile, box_h + label_h, 8
    font_id = ImageFont.load_default(size=label_h - 6)
    font_small = ImageFont.load_default(size=max(12, label_h // 2))

    if todo:
        with ProcessPoolExecutor(
                max_workers=workers,
                # rawpy/LibRaw uses OpenMP, which can deadlock in forked workers.
                mp_context=multiprocessing.get_context("spawn")) as pool:
            for n, name in enumerate(todo):
                if deadline is not None and time.monotonic() >= deadline:
                    print(f"SHEETS INCOMPLETE: {len(todo) - n} of {n_sheets} sheets left - "
                          "run the same command again to continue.")
                    return 3
                chunk = by_sheet[name]
                imgs = pool.map(_tile, [str(cfg.photos_root / r["relpath"]) for r in chunk],
                                [r["kind"] for r in chunk], repeat((cell_w, box_h)))
                sheet = Image.new("RGB", (pad + cols * (cell_w + pad),
                                          pad + rows_n * (cell_h + pad)), (40, 40, 40))
                draw = ImageDraw.Draw(sheet)
                for k, (row, img) in enumerate(zip(chunk, imgs)):
                    x = pad + (k % cols) * (cell_w + pad)
                    y = pad + (k // cols) * (cell_h + pad)
                    if img is None:
                        draw.text((x + 10, y + 10), "preview error", fill=(255, 90, 90),
                                  font=font_small)
                    else:
                        sheet.paste(img, (x + (cell_w - img.width) // 2,
                                          y + (box_h - img.height) // 2))
                    draw.rectangle([x, y + box_h, x + cell_w - 1, y + cell_h - 1], fill=(0, 0, 0))
                    draw.text((x + 8, y + box_h + 2), row["id"], fill=(255, 220, 0), font=font_id)
                    when = row["captured_at"][:16].replace("T", " ")
                    draw.text((x + cell_w - 8, y + box_h + label_h // 2), when,
                              fill=(200, 200, 200), font=font_small, anchor="rm")
                sheet.save(out / name, quality=opts["jpeg_quality"], optimize=True)
                with open(out / DONE_NAME, "a", encoding="utf-8") as fh:
                    fh.write(name + "\n")

    # Remove sheets left over from a previous, larger run (best effort: some sandboxes
    # forbid deletion; index.csv is authoritative either way).
    stale = []
    for old in sorted(out.glob("sheet_*.jpg")):
        try:
            if int(old.stem.split("_")[1]) > n_sheets:
                old.unlink()
        except (ValueError, IndexError):
            continue
        except OSError:
            stale.append(old.name)

    if passed:
        print(f"[sheets {year}] {len(passed)} images on {n_sheets} sheets "
              f"(sheet_001.jpg - sheet_{n_sheets:03d}.jpg) in {out}")
    else:
        print(f"[sheets {year}] nothing to review"
              + ("" if include_reviewed else " (already-reviewed files are skipped)"))
    if stale:
        print(f"note: could not delete {len(stale)} stale sheets from an earlier run "
              f"({stale[0]} ...); ignore them - index.csv lists the current set")
    print("SHEETS COMPLETE")
    return 0
