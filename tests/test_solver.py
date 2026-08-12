"""Safety and determinism checks for the competition solver."""

from __future__ import annotations

from dataclasses import replace

from solver import Objective, Weights, solve
from swiftroute.metrics import evaluate


def test_zero_time_solver_is_valid_and_deterministic(tiny):
    first = solve(tiny, time_limit=0, seed=7)
    second = solve(tiny, time_limit=0, seed=7)
    assert first == second
    assert evaluate(tiny, first).feasible
    assert {oid for route in first for oid in route} == {1, 2}


def test_capacity_is_never_violated(tiny):
    constrained = replace(tiny, vehicle_capacity=3, num_vehicles=1)
    routes = solve(constrained, time_limit=0, seed=7)
    stats = evaluate(constrained, routes)
    assert stats.feasible
    assert stats.orders_served == 1
    assert stats.orders_unserved == 1


def test_unservable_single_order_is_left_out(tiny):
    constrained = replace(tiny, vehicle_capacity=1)
    routes = solve(constrained, time_limit=0, seed=7)
    stats = evaluate(constrained, routes)
    assert stats.feasible
    assert routes == []
    assert stats.unserved_ids == [1, 2]


def test_objective_rewards_removing_distance_when_service_is_equal(tiny):
    objective = Objective(tiny, Weights())
    assert objective.solution_cost([[1, 2]]) < objective.solution_cost([[1], [2]])
