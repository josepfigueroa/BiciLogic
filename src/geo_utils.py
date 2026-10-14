"""Geospatial helpers for BiciLogic.

Correct point-to-network snapping (via the nearest *edge*, not the nearest node)
and shortest-path distance matrices over an OSMnx street graph.

All functions assume a **projected** graph (coordinates in meters), e.g.
``Gp = osmnx.project_graph(G)``, so that geometric projections and access
distances are in meters.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
from shapely.geometry import Point, LineString


def _edge_linestring(G, u, v, k) -> LineString:
    """Geometry of edge (u, v, k); fall back to a straight segment between nodes."""
    data = G.edges[u, v, k]
    if "geometry" in data:
        return data["geometry"]
    return LineString(
        [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
    )


def add_access_node(G, x, y, node_id, edge=None):
    """Insert a virtual node where point (x, y) projects onto its nearest edge.

    Instead of snapping the point to the nearest *node* (which can be a poor
    approximation in the middle of a long edge, and forces an arbitrary choice of
    which endpoint to enter from), we project the point onto the nearest *edge* and
    split that edge with a virtual node. The router then decides on its own which
    endpoint to use, respecting one-way directions.

    G must be projected (meters). Mutates G in place.

    Returns
    -------
    (node_id, access_dist) : the id of the inserted node and the off-network
        'stub' distance from the real point to the network (perpendicular access).
        The stub is entered and left exactly once per stop, so it is a *per-point
        constant* that does not change the optimal visiting order, only the
        reported total distance.
    """
    import osmnx as ox

    if edge is None:
        edge = ox.distance.nearest_edges(G, X=x, Y=y)
    u, v, k = edge

    line = _edge_linestring(G, u, v, k)
    p = Point(x, y)
    s = line.project(p)            # arc length from u to the closest point (meters)
    snap = line.interpolate(s)     # the projected point on the edge
    L = line.length
    access_dist = float(p.distance(snap))

    d_u = s                        # u -> snap
    d_v = L - s                    # snap -> v

    G.add_node(node_id, x=snap.x, y=snap.y)
    # Split the edge in its original direction(s).
    G.add_edge(u, node_id, length=d_u)
    G.add_edge(node_id, v, length=d_v)
    if G.has_edge(v, u):           # two-way street: mirror the reverse direction
        G.add_edge(v, node_id, length=d_v)
        G.add_edge(node_id, u, length=d_u)

    return node_id, access_dist


def distance_matrix(G, nodes, weight="length"):
    """All-pairs shortest-path distances among `nodes` (one Dijkstra per source)."""
    n = len(nodes)
    D = np.full((n, n), np.inf)
    for i, src in enumerate(nodes):
        lengths = nx.single_source_dijkstra_path_length(G, src, weight=weight)
        for j, dst in enumerate(nodes):
            D[i, j] = lengths.get(dst, np.inf)
    return D
