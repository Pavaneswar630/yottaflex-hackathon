from src.config import Scale
from src.exporter import dataset_hashes
from src.generator import generate


def test_parent_and_transaction_counts_are_linked(small_data):
    assert len(small_data["products"]) == 12
    assert len(small_data["machines"]) == 8
    assert len(small_data["production_orders"]) == 40
    assert len(small_data["operations"]) == 160
    assert len(small_data["materials"]) == 24
    assert len({row["operation_id"] for row in small_data["operations"]}) == 160
    order_ids = {row["order_id"] for row in small_data["production_orders"]}
    assert all(row["order_id"] in order_ids for row in small_data["operations"])
    assert all(row["operation_id"].startswith(f"OP-{row['order_id']}-") for row in small_data["operations"])


def test_same_seed_matches_and_different_seed_changes_hashes():
    scale = Scale(skus=8, machines=8, orders=16, materials=16, horizon_days=60)
    first = generate(31, scale)
    assert dataset_hashes(first) == dataset_hashes(generate(31, scale))
    assert dataset_hashes(first) != dataset_hashes(generate(32, scale))
