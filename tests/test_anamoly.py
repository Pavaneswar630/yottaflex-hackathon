import copy

import pytest

from src.anomaly_injector import make_anomaly_scenarios
from src.exporter import dataset_hashes
from src.validator import validate


@pytest.mark.parametrize("expected", [
    "machine_overlap", "precedence_violation", "material_before_availability",
    "outside_shift", "changeover_omitted",
])
def test_each_edge_case_is_isolated_and_detected(small_data, expected):
    original_hashes = dataset_hashes(small_data)
    scenarios, labels = make_anomaly_scenarios(small_data)
    scenario = scenarios[expected]
    report = validate(
        small_data,
        scenario["operation_schedules"],
        scenario["material_consumption_events"],
        scenario["schedule_id"],
    )
    assert [issue["issue_type"] for issue in report["issues"]] == [expected], report["issues"]
    assert any(label["issue_type"] == expected and label["schedule_id"] == scenario["schedule_id"] for label in labels)
    assert dataset_hashes(small_data) == original_hashes


def test_scenario_mutations_do_not_change_clean_schedule(small_data):
    before = copy.deepcopy(small_data["operation_schedules"])
    make_anomaly_scenarios(small_data)
    assert small_data["operation_schedules"] == before
