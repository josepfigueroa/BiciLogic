"""Export the figures embedded in the executed notebooks to ``outputs/``.

The notebooks are committed *with* their outputs, so every figure in
``outputs/`` produced by this script is byte-for-byte what the committed code
generated -- no figure lives in the repo without the cell that made it.

Usage (from the repo root)::

    python tools/export_notebook_figures.py
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (notebook, index of the image among that notebook's outputs, exported name)
FIGURES = [
    ("01_real_map_brussels",      0, "fig_01_shortest_path.png"),
    ("02_single_courier_tsp",     0, "fig_02_stops.png"),
    ("02_single_courier_tsp",     1, "fig_02_annealing_convergence.png"),
    ("03_multi_courier_vrp",      0, "fig_03_vrp_3couriers.png"),
    ("03_multi_courier_vrp",      1, "fig_03_fleet_size_tradeoff.png"),
    ("04_districting",            0, "fig_04_kmeans_zones.png"),
    ("05_districting_balanced",   0, "fig_05_count_balanced_zones.png"),
    ("06_districting_workload",   0, "fig_06_bhh_zone_routes.png"),
]


def notebook_images(stem: str) -> list[bytes]:
    """Every PNG stored in a notebook's cell outputs, in cell order."""
    nb = json.loads((ROOT / "notebooks" / f"{stem}.ipynb").read_text())
    images = []
    for cell in nb["cells"]:
        for out in cell.get("outputs", []):
            png = out.get("data", {}).get("image/png")
            if png is not None:
                images.append(base64.b64decode("".join(png)))
    return images


def main() -> None:
    outdir = ROOT / "outputs"
    outdir.mkdir(exist_ok=True)
    cache: dict[str, list[bytes]] = {}
    for stem, i, name in FIGURES:
        images = cache.setdefault(stem, notebook_images(stem))
        if i >= len(images):
            raise SystemExit(
                f"{stem}.ipynb has {len(images)} stored figures, need index {i}. "
                "Re-run the notebook so its outputs are saved."
            )
        (outdir / name).write_bytes(images[i])
        print(f"{name:38s} <- {stem}.ipynb (figure {i + 1})")


if __name__ == "__main__":
    main()
