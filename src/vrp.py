"""Multi-courier vehicle routing (VRP) on a precomputed distance matrix, via OR-Tools.

OR-Tools optimizes the assignment + ordering only; the distance matrix comes from
the OSMnx street graph (see ``geo_utils.distance_matrix``). OR-Tools holds no map data.
"""
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def solve_vrp(D, n_vehicles, depot=0, objective="makespan", span_coeff=100,
              time_limit_s=5):
    """Solve a k-courier VRP over integer-rounded distances.

    objective:
      - ``"sum"``: minimize total distance across all couriers.
      - ``"makespan"``: minimize the longest single-courier route (workload
        balance), via a large global-span penalty on a distance dimension.

    Returns ``(routes, lengths)`` where ``routes[v]`` is the sequence of matrix
    indices for courier v (starting and ending at the depot) and ``lengths[v]``
    its route distance in meters.
    """
    n = len(D)
    mgr = pywrapcp.RoutingIndexManager(n, n_vehicles, depot)
    routing = pywrapcp.RoutingModel(mgr)

    def cb(i, j):
        return int(round(D[mgr.IndexToNode(i)][mgr.IndexToNode(j)]))

    transit = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    if objective == "makespan":
        routing.AddDimension(transit, 0, 10_000_000, True, "Dist")
        routing.GetDimensionOrDie("Dist").SetGlobalSpanCostCoefficient(span_coeff)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    params.time_limit.FromSeconds(time_limit_s)

    sol = routing.SolveWithParameters(params)
    if sol is None:
        raise RuntimeError("OR-Tools found no solution")

    routes, lengths = [], []
    for v in range(n_vehicles):
        idx, seq, dist = routing.Start(v), [], 0
        while not routing.IsEnd(idx):
            nxt = sol.Value(routing.NextVar(idx))
            dist += routing.GetArcCostForVehicle(idx, nxt, v)
            seq.append(mgr.IndexToNode(idx))
            idx = nxt
        seq.append(mgr.IndexToNode(idx))
        routes.append(seq)
        lengths.append(dist)
    return routes, lengths
