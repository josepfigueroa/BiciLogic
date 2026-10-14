"""TSP solvers over a precomputed distance matrix.

Convention: index 0 is the depot. A tour starts and ends at the depot and visits
every other index exactly once. An `order` is a list of indices starting at the
depot, *without* the trailing return; `tour_distance` adds the return leg.
"""
from itertools import permutations

import numpy as np


def tour_distance(D, order):
    """Total distance of the closed tour depot -> order -> depot (return leg included)."""
    idx = list(order) + [order[0]]
    return float(sum(D[idx[i], idx[i + 1]] for i in range(len(idx) - 1)))


def naive_order(n):
    """Baseline: visit stops in their input order (depot, d1, d2, ...)."""
    return list(range(n))


def nearest_neighbor(D, start=0):
    """Greedy: from the current stop, always jump to the nearest unvisited stop."""
    n = len(D)
    unvisited = set(range(n)) - {start}
    order, current = [start], start
    while unvisited:
        nxt = min(unvisited, key=lambda j: D[current, j])
        order.append(nxt)
        unvisited.discard(nxt)
        current = nxt
    return order


def brute_force_optimal(D, depot=0):
    """Exact optimum by trying every permutation of the non-depot stops.

    Cost is (n-1)! so this is ground truth only for small n (~<=10).
    """
    others = [i for i in range(len(D)) if i != depot]
    best_order, best_cost = None, np.inf
    for perm in permutations(others):
        order = [depot] + list(perm)
        c = tour_distance(D, order)
        if c < best_cost:
            best_cost, best_order = c, order
    return best_order, best_cost


def _reverse_segment(order, i, j):
    """New tour with the segment order[i..j] reversed (depot at index 0 untouched)."""
    return order[:i] + order[i:j + 1][::-1] + order[j + 1:]


def two_opt(D, order):
    """Local search: repeatedly reverse the segment that most shortens the tour.

    A 2-opt move cuts two edges and reconnects them, reversing the segment between.
    We stop at a local optimum (no reversal improves). Note: with an *asymmetric*
    matrix the reversed segment changes direction, so we recompute the full cost
    rather than a cheap 4-edge delta.
    """
    best, best_cost, n = list(order), tour_distance(D, order), len(order)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                cand = _reverse_segment(best, i, j)
                c = tour_distance(D, cand)
                if c < best_cost - 1e-9:
                    best, best_cost, improved = cand, c, True
    return best, best_cost


def _initial_temperature(D, order, rng, n_samples=300, target_accept=0.8):
    """Pick T0 so a typical *worsening* move is accepted ~target_accept of the time."""
    cur = tour_distance(D, order)
    n = len(order)
    deltas = []
    for _ in range(n_samples):
        i, j = sorted(rng.integers(1, n, size=2))
        if i == j:
            continue
        d = tour_distance(D, _reverse_segment(order, i, j)) - cur
        if d > 0:
            deltas.append(d)
    if not deltas:
        return 1.0
    return float(-np.mean(deltas) / np.log(target_accept))


def simulated_annealing(D, order, T0=None, alpha=0.95, iters_per_T=200,
                        T_min=1e-2, seed=0):
    """Simulated annealing for the TSP (the Metropolis algorithm).

    State = a tour; energy E = tour length; proposal = a random 2-opt reversal.
    A move with energy change dE is accepted if dE <= 0, else with probability
    exp(-dE / T). The temperature T cools geometrically (T <- alpha * T), so we
    explore freely when hot and behave greedily when cold.

    Returns (best_order, best_cost, history) where history is a list of
    (T, current_cost, best_cost) sampled once per temperature level.
    """
    rng = np.random.default_rng(seed)
    current = list(order)
    cur_cost = tour_distance(D, current)
    best, best_cost = list(current), cur_cost
    n = len(current)
    T = _initial_temperature(D, order, rng) if T0 is None else T0

    history = []
    while T > T_min:
        for _ in range(iters_per_T):
            i, j = sorted(rng.integers(1, n, size=2))
            if i == j:
                continue
            cand = _reverse_segment(current, i, j)
            c = tour_distance(D, cand)
            dE = c - cur_cost
            if dE <= 0 or rng.random() < np.exp(-dE / T):
                current, cur_cost = cand, c
                if cur_cost < best_cost:
                    best, best_cost = list(current), cur_cost
        history.append((T, cur_cost, best_cost))
        T *= alpha
    return best, best_cost, history
