"""How much of the zoning comparison in notebook 06 is the partition, and how much is the solver?

Every routed workload reported in notebook 06 comes from OR-Tools with a 2-second
budget per zone. OR-Tools is an *anytime* heuristic, so those workloads are upper
bounds -- and possibly upper bounds of differing tightness across partitions. If so,
a partition could look balanced only because the solver did equally mediocre work on
all of its zones.

This script rebuilds the three partitions exactly as notebook 06 does, then re-routes
them at several solver budgets. The partitions are held fixed, so the only variable is
the routing budget.

Results are written to ``outputs/solver_budget_sensitivity.json``.

Usage (from the repo root)::

    python tools/solver_budget_sensitivity.py

Runtime is roughly ``sum(BUDGETS) * REPEATS * 3 partitions * 4 zones`` seconds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
from scipy.optimize import linear_sum_assignment
from shapely.geometry import MultiPoint
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from geo_utils import distance_matrix          # noqa: E402
from vrp import solve_vrp                      # noqa: E402

BUDGETS = [2, 10, 30]     # seconds per zone given to OR-Tools
REPEATS = 2               # repeats per budget, to separate randomness from budget
BETA = 1.347              # beta_net as calibrated in notebook 06 (held fixed here)


def build_instance():
    """Reproduce notebook 06's graph, demand and three partitions, bit for bit."""
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ROOT / "notebooks" / "cache")

    G = ox.graph_from_point((50.830, 4.370), dist=3000, network_type="bike", simplify=True)
    Gp = ox.project_graph(G)
    Gs = Gp.subgraph(max(nx.strongly_connected_components(Gp), key=len)).copy()
    nodes = list(Gs.nodes)
    coords = np.array([[Gs.nodes[n]["x"], Gs.nodes[n]["y"]] for n in nodes])

    rng = np.random.default_rng(3)
    hot = coords[rng.choice(len(nodes), size=4, replace=False)]
    d_near = np.sqrt(((coords[:, None, :] - hot[None, :, :]) ** 2).sum(-1)).min(axis=1)
    w = np.exp(-d_near / 500.0) + 0.15
    w /= w.sum()
    didx = rng.choice(len(nodes), size=200, replace=False, p=w)
    demand_nodes = [nodes[i] for i in didx]
    demand_xy = coords[didx]
    n, k = len(demand_nodes), 4

    depot = ox.nearest_nodes(Gs, X=demand_xy[:, 0].mean(), Y=demand_xy[:, 1].mean())
    ddepot = nx.single_source_dijkstra_path_length(Gs, depot, weight="length")

    # (1) k-means
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(demand_xy)
    labels_km = km.labels_

    # (2) count-balanced: tiled Hungarian on network distance
    seeds = ox.nearest_nodes(Gs, X=km.cluster_centers_[:, 0], Y=km.cluster_centers_[:, 1])
    netdist = np.zeros((n, k))
    for z, s in enumerate(seeds):
        dd = nx.single_source_dijkstra_path_length(Gs, s, weight="length")
        netdist[:, z] = [dd.get(nd, 1e9) for nd in demand_nodes]
    cap = int(np.ceil(n / k))
    row, col = linear_sum_assignment(np.repeat(netdist, cap, axis=1))
    labels_bal = np.empty(n, dtype=int)
    labels_bal[row] = col // cap

    # (3) BHH workload-balanced: greedy boundary swaps on the estimated workload
    def hull_area(xy):
        return MultiPoint(xy).convex_hull.area if len(xy) >= 3 else 0.0

    def bhh_w(idx, center):
        return 2 * ddepot.get(center, 0) + BETA * np.sqrt(len(idx) * hull_area(demand_xy[idx]))

    labels = labels_bal.copy()
    best_labels, best_ratio = labels.copy(), np.inf
    for _ in range(80):
        zones = [np.where(labels == z)[0] for z in range(k)]
        centers = [ox.nearest_nodes(Gs, X=demand_xy[zi, 0].mean(), Y=demand_xy[zi, 1].mean())
                   for zi in zones]
        wl = np.array([bhh_w(zones[z], centers[z]) for z in range(k)])
        ratio = wl.max() / wl.min()
        if ratio < best_ratio:
            best_ratio, best_labels = ratio, labels.copy()
        if ratio < 1.05:
            break
        zmax, zmin = int(wl.argmax()), int(wl.argmin())
        dmin = nx.single_source_dijkstra_path_length(Gs, centers[zmin], weight="length")
        dmax = nx.single_source_dijkstra_path_length(Gs, centers[zmax], weight="length")
        cand = zones[zmax]
        score = [dmin.get(demand_nodes[i], 1e9) - dmax.get(demand_nodes[i], 1e9) for i in cand]
        labels[cand[int(np.argmin(score))]] = zmin

    partitions = {
        "k-means": labels_km,
        "count-balanced": labels_bal,
        "BHH": best_labels,
    }
    return Gs, depot, demand_nodes, partitions, k


def main() -> None:
    Gs, depot, demand_nodes, partitions, k = build_instance()
    n = len(demand_nodes)

    for name, lab in partitions.items():
        print(f"{name:15s} counts {np.bincount(lab, minlength=k).tolist()}")

    # Build each zone's distance matrix once; only the routing budget varies below.
    mats = {
        name: [distance_matrix(Gs, [depot] + [demand_nodes[i] for i in range(n) if lab[i] == z])
               for z in range(k)]
        for name, lab in partitions.items()
    }

    results = []
    for budget in BUDGETS:
        for rep in range(REPEATS):
            for name in partitions:
                loads = np.array([solve_vrp(m, 1, objective="sum", time_limit_s=budget)[1][0]
                                  for m in mats[name]])
                results.append({
                    "budget_s": budget,
                    "repeat": rep,
                    "partition": name,
                    "zone_km": (loads / 1000).round(3).tolist(),
                    "busiest_km": round(float(loads.max()) / 1000, 3),
                    "lightest_km": round(float(loads.min()) / 1000, 3),
                    "total_km": round(float(loads.sum()) / 1000, 3),
                    "imbalance": round(float(loads.max() / loads.min()), 4),
                })
                r = results[-1]
                print(f"budget={budget:2d}s rep{rep} {name:15s} "
                      f"busiest {r['busiest_km']:6.2f} imb {r['imbalance']:.3f} "
                      f"total {r['total_km']:6.1f}")

    out = ROOT / "outputs" / "solver_budget_sensitivity.json"
    out.write_text(json.dumps(
        {"beta_net": BETA, "budgets_s": BUDGETS, "repeats": REPEATS, "results": results},
        indent=2))
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
