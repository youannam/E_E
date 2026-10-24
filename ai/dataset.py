"""
Synthetic training and evaluation dataset.

We do not have real insider-threat data (and must not monitor real employees), so the
model is trained on synthetic activity from the simulator. This is clearly a limitation:
results on this data show the pipeline works, NOT how well it would work in a real company.

Layout of the generated data (all fixed by the seed, so it is reproducible):
  * NUM_USERS synthetic employees (different from the demo employees)
  * NUM_DAYS calendar days, weekends skipped
  * The first (NUM_DAYS - TEST_DAYS) days: only normal behavior  -> training period
  * The last TEST_DAYS days: mostly normal, but some user-days are replaced by
    scenario days (B-H)                                          -> test period
Labels: 1 = suspicious scenario day (B-G), 0 = normal day or benign exception (H).
"""

import random
from datetime import date, timedelta

import pandas as pd

from simulator.catalog import WEEKEND_DAYS, make_synthetic_population
from simulator.generator import generate_normal_day
from simulator.scenarios import SCENARIOS, run_scenario

NUM_USERS = 40
NUM_DAYS = 90
TEST_DAYS = 30
END_DATE = date(2026, 6, 30)  # fixed so the dataset never changes between runs
INJECTION_RATE = 0.10  # share of test-period user-days replaced by a scenario day
DEFAULT_SEED = 7

EVENT_COLUMNS = ["user_id", "timestamp", "event_type", "resource", "sensitivity", "file_size_bytes", "device_id", "scenario"]


def training_population(seed: int = DEFAULT_SEED):
    """The synthetic employees of the dataset (the first thing drawn from the seeded generator)."""
    return make_synthetic_population(NUM_USERS, random.Random(seed))


def generate_dataset(seed: int = DEFAULT_SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (events, labels).
      events: one row per raw event
      labels: one row per user-day with columns user_id, day, period, label, scenario
    """
    rng = random.Random(seed)
    employees = make_synthetic_population(NUM_USERS, rng)
    injected_scenarios = [scenario_id for scenario_id in SCENARIOS if scenario_id != "NORMAL_USER"]
    first_day = END_DATE - timedelta(days=NUM_DAYS - 1)
    test_start = END_DATE - timedelta(days=TEST_DAYS - 1)

    event_rows = []
    label_rows = []
    for offset in range(NUM_DAYS):
        day = first_day + timedelta(days=offset)
        if day.weekday() in WEEKEND_DAYS:
            continue
        period = "test" if day >= test_start else "train"
        for employee in employees:
            scenario_id = "NORMAL_USER"
            if period == "test" and rng.random() < INJECTION_RATE:
                scenario_id = rng.choice(injected_scenarios)

            if scenario_id == "NORMAL_USER":
                events = generate_normal_day(employee, day, rng)
            else:
                events = run_scenario(scenario_id, employee, day, seed=rng.randint(0, 10**6), intensity=rng.choice([1, 2]))

            for event in events:
                event_rows.append({
                    "user_id": employee.username,
                    "timestamp": event["timestamp"],
                    "event_type": event["event_type"],
                    "resource": event["resource"],
                    "sensitivity": event["sensitivity"],
                    "file_size_bytes": event["file_size_bytes"],
                    "device_id": event["device_id"],
                    "scenario": scenario_id,
                })
            label_rows.append({
                "user_id": employee.username,
                "day": day,
                "period": period,
                "label": 1 if SCENARIOS[scenario_id].suspicious else 0,
                "scenario": scenario_id,
            })

    return pd.DataFrame(event_rows, columns=EVENT_COLUMNS), pd.DataFrame(label_rows)
