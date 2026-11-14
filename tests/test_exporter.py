import csv
import json

from src.anomaly_injector import make_anomaly_scenarios
from src.exporter import dataset_hashes, export_dataset
from src.validator import validate


def test_exports_csv_json_sql_and_keeps_labels_separate(tmp_path, small_data):
    report = validate(small_data)
    scenarios, labels = make_anomaly_scenarios(small_data)
    output = tmp_path / "data"
    export_dataset(
        small_data, output, report, scenarios, labels, dataset_hashes(small_data),
        20261022, {"orders": 40}, {"checked": True, "identical": True},
    )
    assert (output / "clean" / "products.csv").exists()
    assert json.loads((output / "clean" / "products.json").read_text(encoding="utf-8"))
    assert "CREATE TABLE" in (output / "clean" / "seed.sql").read_text(encoding="utf-8")
    truth_path = output / "ground_truth" / "ground_truth.csv"
    with truth_path.open(encoding="utf-8") as truth_file:
        assert len(list(csv.DictReader(truth_file))) == 5
    assert not (output / "clean" / "ground_truth.csv").exists()
