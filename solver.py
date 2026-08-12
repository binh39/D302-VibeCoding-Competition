#!/usr/bin/env python3
"""Competition solver for the SwiftRoute challenge.

The exact contest cost is hidden.  This solver therefore exposes every surrogate-cost
weight on the command line, while providing conservative defaults that strongly prefer
serving orders and avoiding severe lateness/overtime.

Example:
    python solver.py --orders data/sample_orders.csv --out NguyenDinhBinh.json
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from swiftroute.io_csv import read_instances
from swiftroute.io_submission import load_submission, write_submission
from swiftroute.metrics import check_hard_constraints, evaluate
from swiftroute.model import Instance, Routes


@dataclass(frozen=True)
class Weights:
    """Tunable surrogate for the organizer's hidden operating cost."""

    distance: float = 1.0
    vehicle: float = 50.0
    lateness: float = 2.0
    lateness_squared: float = 0.05
    overtime: float = 3.0
    overtime_squared: float = 0.03
    unserved: float = 500.0
    unserved_demand: float = 50.0


@dataclass(frozen=True)
class RouteMetrics:
    load: int
    distance: float
    lateness: float
    lateness_squared: float
    overtime: float


class Objective:
    """Fast route simulation and a bounded memoization cache."""

    def __init__(self, instance: Instance, weights: Weights) -> None:
        self.instance = instance
        self.weights = weights
        self.ids = instance.order_ids
        self.order = {o.id: o for o in instance.orders}
        self.index = {oid: i + 1 for i, oid in enumerate(self.ids)}
        points = [(instance.depot_x, instance.depot_y)] + [
            (o.x, o.y) for o in instance.orders
        ]
        self.distance = [
            [math.hypot(ax - bx, ay - by) for bx, by in points]
            for ax, ay in points
        ]
        self._cache: dict[tuple[int, ...], RouteMetrics] = {}

    def route_metrics(self, route: Sequence[int]) -> RouteMetrics:
        key = tuple(route)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        t = float(self.instance.shift_start)
        previous = 0
        distance = 0.0
        load = 0
        lateness = 0.0
        lateness_squared = 0.0
        for oid in key:
            idx = self.index[oid]
            step = self.distance[previous][idx]
            distance += step
            t += step / self.instance.speed
            order = self.order[oid]
            t = max(t, float(order.ready_time))
            late = max(0.0, t - order.due_time)
            lateness += late
            lateness_squared += late * late
            t += order.service_time
            load += order.demand
            previous = idx

        distance += self.distance[previous][0]
        t += self.distance[previous][0] / self.instance.speed
        result = RouteMetrics(
            load=load,
            distance=distance,
            lateness=lateness,
            lateness_squared=lateness_squared,
            overtime=max(0.0, t - self.instance.shift_end),
        )
        if len(self._cache) >= 100_000:
            self._cache.clear()
        self._cache[key] = result
        return result

    def route_cost(self, route: Sequence[int]) -> float:
        if not route:
            return 0.0
        m = self.route_metrics(route)
        w = self.weights
        return (
            w.vehicle
            + w.distance * m.distance
            + w.lateness * m.lateness
            + w.lateness_squared * m.lateness_squared
            + w.overtime * m.overtime
            + w.overtime_squared * m.overtime * m.overtime
        )

    def unserved_cost(self, oid: int) -> float:
        w = self.weights
        return w.unserved + w.unserved_demand * self.order[oid].demand

    def solution_cost(self, routes: Sequence[Sequence[int]]) -> float:
        served = {oid for route in routes for oid in route}
        return sum(self.route_cost(route) for route in routes) + sum(
            self.unserved_cost(oid) for oid in self.ids if oid not in served
        )

    def candidate_positions(
        self, route: Sequence[int], oid: int, max_positions: int = 14
    ) -> list[int]:
        """Keep spatially promising insertion positions, plus both route ends."""
        if len(route) + 1 <= max_positions:
            return list(range(len(route) + 1))
        node = self.index[oid]
        ranked: list[tuple[float, int]] = []
        for pos in range(len(route) + 1):
            before = 0 if pos == 0 else self.index[route[pos - 1]]
            after = 0 if pos == len(route) else self.index[route[pos]]
            delta = (
                self.distance[before][node]
                + self.distance[node][after]
                - self.distance[before][after]
            )
            ranked.append((delta, pos))
        positions = {0, len(route)}
        positions.update(pos for _, pos in sorted(ranked)[: max_positions - 2])
        return sorted(positions)


def _copy_routes(routes: Sequence[Sequence[int]]) -> Routes:
    return [list(route) for route in routes if route]


def _loads(objective: Objective, routes: Sequence[Sequence[int]]) -> list[int]:
    return [objective.route_metrics(route).load for route in routes]


def _insertion_options(
    objective: Objective,
    routes: Routes,
    loads: list[int],
    oid: int,
    max_positions: int = 14,
) -> list[tuple[float, int, int]]:
    """Return (total-cost delta, route index, position), cheapest first."""
    instance = objective.instance
    demand = objective.order[oid].demand
    options: list[tuple[float, int, int]] = []
    empty_seen = False
    for ri, route in enumerate(routes):
        if not route:
            if empty_seen:
                continue
            empty_seen = True
        if loads[ri] + demand > instance.vehicle_capacity:
            continue
        old_cost = objective.route_cost(route)
        for pos in objective.candidate_positions(route, oid, max_positions):
            candidate = route[:pos] + [oid] + route[pos:]
            delta = objective.route_cost(candidate) - old_cost - objective.unserved_cost(oid)
            options.append((delta, ri, pos))
    options.sort(key=lambda item: item[0])
    return options


def _ordered_ids(objective: Objective, mode: str, rng: random.Random) -> list[int]:
    inst = objective.instance
    orders = list(inst.orders)
    if mode == "due":
        orders.sort(key=lambda o: (o.due_time, o.ready_time, o.due_time - o.ready_time))
    elif mode == "tight":
        orders.sort(key=lambda o: (o.due_time - o.ready_time, o.due_time, -o.demand))
    elif mode == "ready":
        orders.sort(key=lambda o: (o.ready_time, o.due_time, -o.demand))
    elif mode.startswith("sweep"):
        reverse = mode.endswith("reverse")
        orders.sort(
            key=lambda o: math.atan2(o.y - inst.depot_y, o.x - inst.depot_x),
            reverse=reverse,
        )
    else:
        rng.shuffle(orders)
        orders.sort(
            key=lambda o: o.due_time + rng.uniform(-120.0, 120.0),
        )
    return [o.id for o in orders]


def _sequential_construction(
    objective: Objective, mode: str, rng: random.Random
) -> Routes:
    routes: Routes = [[] for _ in range(objective.instance.num_vehicles)]
    loads = [0] * len(routes)
    for oid in _ordered_ids(objective, mode, rng):
        options = _insertion_options(objective, routes, loads, oid)
        if not options or options[0][0] >= 0.0:
            continue
        _, ri, pos = options[0]
        routes[ri].insert(pos, oid)
        loads[ri] += objective.order[oid].demand
    return _copy_routes(routes)


def _regret_repair(
    objective: Objective,
    routes: Routes,
    candidate_ids: Iterable[int],
    rng: random.Random,
    deadline: float,
) -> Routes:
    """Regret-2 insertion; orders that are too expensive remain unserved."""
    routes = _copy_routes(routes)
    while len(routes) < objective.instance.num_vehicles:
        routes.append([])
    loads = _loads(objective, routes)
    pending = list(dict.fromkeys(candidate_ids))

    while pending:
        if time.perf_counter() >= deadline:
            break
        # Full regret is useful for small repairs.  Bound the pool on large instances.
        if len(pending) <= 24:
            pool = pending
        else:
            difficult = sorted(
                pending,
                key=lambda oid: (
                    objective.order[oid].due_time - objective.order[oid].ready_time,
                    objective.order[oid].due_time,
                    -objective.order[oid].demand,
                ),
            )[:16]
            random_part = rng.sample(pending, min(8, len(pending)))
            pool = list(dict.fromkeys(difficult + random_part))

        choice: tuple[float, float, int, list[tuple[float, int, int]]] | None = None
        for oid in pool:
            options = _insertion_options(objective, routes, loads, oid, max_positions=12)
            if not options:
                rank = (math.inf, math.inf, oid, options)
            else:
                second = options[1][0] if len(options) > 1 else objective.unserved_cost(oid)
                regret = second - options[0][0]
                # Higher regret first; on ties insert the more beneficial order.
                rank = (regret, -options[0][0], oid, options)
            if choice is None or rank[:2] > choice[:2]:
                choice = rank

        assert choice is not None
        _, _, oid, options = choice
        pending.remove(oid)
        if not options or options[0][0] >= 0.0:
            continue
        _, ri, pos = options[0]
        routes[ri].insert(pos, oid)
        loads[ri] += objective.order[oid].demand

    return _copy_routes(routes)


def _remove_ids(routes: Routes, removed: set[int]) -> Routes:
    return [[oid for oid in route if oid not in removed] for route in routes if route]


def _destroy_random(routes: Routes, count: int, rng: random.Random) -> set[int]:
    served = [oid for route in routes for oid in route]
    return set(rng.sample(served, min(count, len(served))))


def _destroy_related(
    objective: Objective, routes: Routes, count: int, rng: random.Random
) -> set[int]:
    served = [oid for route in routes for oid in route]
    if not served:
        return set()
    seed = rng.choice(served)
    so = objective.order[seed]
    horizon = max(1, objective.instance.shift_end - objective.instance.shift_start)
    scale = max(1.0, max(objective.distance[0]))

    def relatedness(oid: int) -> float:
        o = objective.order[oid]
        spatial = objective.distance[objective.index[seed]][objective.index[oid]] / scale
        temporal = (abs(so.ready_time - o.ready_time) + abs(so.due_time - o.due_time)) / (
            2 * horizon
        )
        demand = abs(so.demand - o.demand) / max(1, objective.instance.vehicle_capacity)
        return spatial + 0.7 * temporal + 0.2 * demand + rng.random() * 0.05

    return set(sorted(served, key=relatedness)[:count])


def _destroy_worst(
    objective: Objective, routes: Routes, count: int, rng: random.Random
) -> set[int]:
    contributions: list[tuple[float, int]] = []
    for route in routes:
        old = objective.route_cost(route)
        for pos, oid in enumerate(route):
            shortened = route[:pos] + route[pos + 1 :]
            saving = old - objective.route_cost(shortened)
            contributions.append((saving * rng.uniform(0.9, 1.1), oid))
    contributions.sort(reverse=True)
    return {oid for _, oid in contributions[:count]}


def _destroy_route(routes: Routes, rng: random.Random) -> set[int]:
    if not routes:
        return set()
    # Removing a shorter route gives repair a realistic chance to eliminate a vehicle.
    candidates = sorted(routes, key=len)[: max(1, len(routes) // 2)]
    return set(rng.choice(candidates))


def _two_opt(objective: Objective, routes: Routes, rng: random.Random) -> Routes:
    """A small first-improvement 2-opt pass on one route."""
    candidates = [i for i, route in enumerate(routes) if len(route) >= 4]
    if not candidates:
        return routes
    ri = rng.choice(candidates)
    route = routes[ri]
    old_cost = objective.route_cost(route)
    for _ in range(min(20, len(route) * 2)):
        left, right = sorted(rng.sample(range(len(route)), 2))
        if right - left < 2:
            continue
        changed = route[:left] + list(reversed(route[left : right + 1])) + route[right + 1 :]
        if objective.route_cost(changed) + 1e-9 < old_cost:
            routes = _copy_routes(routes)
            routes[ri] = changed
            return routes
    return routes


def _roulette(weights: dict[str, float], rng: random.Random) -> str:
    total = sum(weights.values())
    pick = rng.random() * total
    for name, weight in weights.items():
        pick -= weight
        if pick <= 0:
            return name
    return next(iter(weights))


def solve(
    instance: Instance,
    *,
    time_limit: float = 5.0,
    seed: int = 302,
    weights: Weights | None = None,
    initial_routes: Routes | None = None,
) -> Routes:
    """Build and improve a valid solution until the per-instance deadline."""
    weights = weights or Weights()
    objective = Objective(instance, weights)
    rng = random.Random(f"{seed}:{instance.instance_id}")
    deadline = time.perf_counter() + max(0.0, time_limit)

    best: Routes
    best_cost: float
    if initial_routes is not None and not check_hard_constraints(instance, initial_routes):
        best = _copy_routes(initial_routes)
        best_cost = objective.solution_cost(best)
    else:
        # Deterministic fallback, used when there is no valid incumbent.
        best = _sequential_construction(objective, "due", rng)
        best_cost = objective.solution_cost(best)

    if time.perf_counter() >= deadline:
        return _copy_routes(best)

    for mode in ("tight", "ready", "sweep", "sweep_reverse", "random"):
        if time.perf_counter() >= deadline:
            break
        candidate = _sequential_construction(objective, mode, rng)
        cost = objective.solution_cost(candidate)
        if cost < best_cost:
            best, best_cost = candidate, cost

    if time.perf_counter() >= deadline:
        return _copy_routes(best)

    current = _copy_routes(best)
    current_cost = best_cost
    temperature = max(1.0, 0.015 * best_cost / math.sqrt(max(1, instance.n)))
    operators = {"random": 1.0, "related": 1.0, "worst": 1.0, "route": 0.7}
    stagnation = 0

    while time.perf_counter() < deadline:
        served_count = sum(map(len, current))
        if served_count == 0:
            candidate_ids = instance.order_ids
            candidate = _regret_repair(objective, [], candidate_ids, rng, deadline)
            removed: set[int] = set(candidate_ids)
            operator = "random"
        else:
            low = max(2, int(0.04 * instance.n))
            high = max(low, min(30, int(0.20 * instance.n) + 1))
            count = rng.randint(low, high)
            operator = _roulette(operators, rng)
            if operator == "random":
                removed = _destroy_random(current, count, rng)
            elif operator == "related":
                removed = _destroy_related(objective, current, count, rng)
            elif operator == "worst":
                removed = _destroy_worst(objective, current, count, rng)
            else:
                removed = _destroy_route(current, rng)

            partial = _remove_ids(current, removed)
            served_after = {oid for route in partial for oid in route}
            unserved = [oid for oid in instance.order_ids if oid not in served_after]
            # Reconsider a bounded number of orders previously left out as well.
            if len(unserved) > len(removed) + 12:
                extras = [oid for oid in unserved if oid not in removed]
                extras = rng.sample(extras, min(12, len(extras)))
                candidate_ids = list(removed) + extras
            else:
                candidate_ids = unserved
            candidate = _regret_repair(objective, partial, candidate_ids, rng, deadline)
            candidate = _two_opt(objective, candidate, rng)

        if time.perf_counter() >= deadline and not candidate:
            break
        candidate_cost = objective.solution_cost(candidate)
        delta = candidate_cost - current_cost
        accepted = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9))
        reward = 0.1
        if candidate_cost + 1e-9 < best_cost:
            best, best_cost = _copy_routes(candidate), candidate_cost
            reward = 5.0
            stagnation = 0
        else:
            stagnation += 1
            if delta < 0:
                reward = 2.0
            elif accepted:
                reward = 0.5
        if accepted:
            current, current_cost = candidate, candidate_cost
        operators[operator] = 0.9 * operators[operator] + 0.1 * reward
        temperature *= 0.998

        if stagnation >= 150:
            current, current_cost = _copy_routes(best), best_cost
            temperature = max(temperature, 0.005 * best_cost / math.sqrt(max(1, instance.n)))
            stagnation = 0

    return _copy_routes(best)


def _weights_from_args(args: argparse.Namespace) -> Weights:
    return Weights(
        distance=args.distance_weight,
        vehicle=args.vehicle_weight,
        lateness=args.lateness_weight,
        lateness_squared=args.lateness_squared_weight,
        overtime=args.overtime_weight,
        overtime_squared=args.overtime_squared_weight,
        unserved=args.unserved_weight,
        unserved_demand=args.unserved_demand_weight,
    )


def _print_summary(instance: Instance, routes: Routes, elapsed: float) -> None:
    summary = evaluate(instance, routes).public_summary()
    print(
        f"{instance.instance_id}: {summary['total_distance_km']:8.1f} km  "
        f"{summary['vehicles_used']:2d} xe  bỏ {summary['orders_unserved']:3d} đơn  "
        f"trễ {summary['total_lateness_min']:8.1f} phút  "
        f"ngoài ca {summary['total_overtime_min']:7.1f} phút  ({elapsed:.1f}s)",
        flush=True,
    )


def _checkpoint(path: Path, team: str, solutions: dict[str, Routes]) -> None:
    """Atomically replace the submission so interruption cannot leave broken JSON."""
    temporary = path.with_name(path.name + ".tmp")
    write_submission(temporary, team, solutions)
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orders", required=True, type=Path, help="CSV đề bài")
    parser.add_argument("--out", type=Path, default=Path("NguyenDinhBinh.json"))
    parser.add_argument("--team", default="NguyenDinhBinh")
    parser.add_argument("--time-limit", type=float, default=5.0, help="giây mỗi instance")
    parser.add_argument("--total-time-limit", type=float, default=0.0, help="0 = không giới hạn")
    parser.add_argument("--seed", type=int, default=302)
    parser.add_argument("--resume", type=Path, help="dùng submission cũ làm incumbent")
    parser.add_argument("--distance-weight", type=float, default=Weights.distance)
    parser.add_argument("--vehicle-weight", type=float, default=Weights.vehicle)
    parser.add_argument("--lateness-weight", type=float, default=Weights.lateness)
    parser.add_argument(
        "--lateness-squared-weight", type=float, default=Weights.lateness_squared
    )
    parser.add_argument("--overtime-weight", type=float, default=Weights.overtime)
    parser.add_argument(
        "--overtime-squared-weight", type=float, default=Weights.overtime_squared
    )
    parser.add_argument("--unserved-weight", type=float, default=Weights.unserved)
    parser.add_argument(
        "--unserved-demand-weight", type=float, default=Weights.unserved_demand
    )
    args = parser.parse_args(argv)

    if args.time_limit < 0 or args.total_time_limit < 0:
        parser.error("time limit không được âm")
    weights = _weights_from_args(args)
    if any(value < 0 for value in weights.__dict__.values()):
        parser.error("cost weight không được âm")

    instances = read_instances(args.orders)
    resumed: dict[str, Routes] = {}
    if args.resume:
        resumed = load_submission(args.resume).solutions

    # Produce a complete valid fallback file first.  Every later instance replaces one
    # entry and is checkpointed immediately.
    solutions: dict[str, Routes] = {}
    for instance in instances:
        old = resumed.get(instance.instance_id)
        if old is not None and not check_hard_constraints(instance, old):
            solutions[instance.instance_id] = _copy_routes(old)
        else:
            solutions[instance.instance_id] = solve(
                instance, time_limit=0.0, seed=args.seed, weights=weights
            )
    _checkpoint(args.out, args.team, solutions)

    global_deadline = (
        time.perf_counter() + args.total_time_limit if args.total_time_limit > 0 else math.inf
    )
    for index, instance in enumerate(instances):
        remaining = global_deadline - time.perf_counter()
        if remaining <= 0:
            print("Đã hết total-time-limit; giữ các nghiệm fallback còn lại.")
            break
        remaining_instances = len(instances) - index
        fair_share = remaining / remaining_instances if math.isfinite(remaining) else math.inf
        limit = min(args.time_limit, max(0.0, fair_share - 0.05))
        started = time.perf_counter()
        routes = solve(
            instance,
            time_limit=limit,
            seed=args.seed,
            weights=weights,
            initial_routes=solutions[instance.instance_id],
        )
        if check_hard_constraints(instance, routes):
            print(f"CẢNH BÁO: giữ fallback hợp lệ cho {instance.instance_id}", file=sys.stderr)
        else:
            solutions[instance.instance_id] = routes
            _checkpoint(args.out, args.team, solutions)
        _print_summary(instance, solutions[instance.instance_id], time.perf_counter() - started)

    print(f"\nĐã ghi và checkpoint: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
