import pytest
from pydantic import ValidationError

from src.schemas import MODEL_BY_TABLE, Product, data_dictionary


def test_primary_id_conventions_are_enforced():
    Product.model_validate({"sku": "PROD-2026-000001", "name": "Widget", "family": "FAM-01", "active": True})
    with pytest.raises(ValidationError):
        Product.model_validate({"sku": "SKU-1", "name": "Widget", "family": "FAM-01", "active": True})


def test_pydantic_fields_and_metadata_match_data_dictionary():
    dictionary = data_dictionary()["entities"]
    assert set(MODEL_BY_TABLE) == set(dictionary)
    for table, model in MODEL_BY_TABLE.items():
        entity = dictionary[table]
        fields = {field["name"]: field for field in entity["fields"]}
        assert set(model.model_fields) == set(fields)
        for name, model_field in model.model_fields.items():
            assert model_field.is_required() == fields[name]["required"]
            assert {"allowed_values", "units", "unique", "validation"} <= fields[name].keys()
