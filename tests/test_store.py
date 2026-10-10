from __future__ import annotations

import json
import math
from typing import Any

import pytest

from bazaar.llm import ToolCall
from bazaar.store import Store, execute, normalize_phone, tool_specs


def call(store: Store, name: str, **arguments: Any) -> tuple[bool, Any]:
    outcome = execute(store, ToolCall(id="t", name=name, arguments=arguments))
    return outcome.ok, json.loads(outcome.content)


def stock(store: Store, sku: str) -> int:
    for product in store.state.products.values():
        for variant in product.variants:
            if variant.sku == sku:
                return variant.stock
    raise KeyError(sku)


@pytest.fixture
def store() -> Store:
    return Store.from_seed()


def test_each_from_seed_is_independent() -> None:
    a, b = Store.from_seed(), Store.from_seed()
    a.state.orders.clear()
    assert b.state.orders


def test_seed_orders_are_internally_consistent(store: Store) -> None:
    for order in store.state.orders.values():
        assert order.subtotal == sum(i.unit_price * i.qty for i in order.items), order.id
        assert order.total == order.subtotal - order.discount + order.shipping_fee, order.id
        grams = sum(store.state.products[i.product_id].weight_grams * i.qty for i in order.items)
        zone = store.state.shipping_zones[order.city.lower()]
        assert order.shipping_fee == max(1, math.ceil(grams / 1000)) * zone.fee_per_kg, order.id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("+62 812-3456-7801", "081234567801"), ("0812 3456 7801", "081234567801")],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


def test_search_finds_by_keyword_and_color(store: Store) -> None:
    ok, result = call(store, "search_products", query="kemeja linen sage")
    assert ok
    assert result[0]["product_id"] == "P01"


def test_shipping_rounds_weight_up_per_kg(store: Store) -> None:
    ok, result = call(
        store, "calculate_shipping", city="jakarta", items=[{"sku": "HDF-ABU-L", "qty": 2}]
    )
    assert ok
    assert result["weight_kg"] == 2  # 1400 g -> 2 kg
    assert result["shipping_fee"] == 36000
    assert result["cod_available"] is True


def test_create_order_happy_path(store: Store) -> None:
    before = stock(store, "CCS-KHK-30")
    ok, order = call(
        store,
        "create_order",
        customer_name="Fajar",
        customer_phone="+62 813-0000-0001",
        city="Jakarta",
        address="Jl. Kemang Raya No. 1",
        items=[{"sku": "CCS-KHK-30", "qty": 2}],
        payment_method="transfer",
        voucher_code="hemat20",
    )
    assert ok, order
    assert order["id"] == "ORD-1009"
    assert order["subtotal"] == 578000
    assert order["discount"] == 50000  # 20% capped at 50k
    assert order["shipping_fee"] == 18000
    assert order["total"] == 546000
    assert order["status"] == "pending_payment"
    assert order["customer_phone"] == "081300000001"
    assert stock(store, "CCS-KHK-30") == before - 2


@pytest.mark.parametrize(
    ("overrides", "error_fragment"),
    [
        ({"items": [{"sku": "KOK-HTM-L", "qty": 3}]}, "Insufficient stock"),
        ({"items": [{"sku": "KLP-NVY-L", "qty": 1}]}, "Insufficient stock"),
        ({"voucher_code": "AGUSTUSAN"}, "expired"),
        ({"voucher_code": "NEWBIE25", "items": [{"sku": "TBK-NAT-ALL", "qty": 1}]}, "minimum"),
        ({"city": "Medan", "payment_method": "cod"}, "COD is not available"),
        ({"city": "Tokyo"}, "No shipping"),
        ({"items": [{"sku": "XXX", "qty": 1}]}, "not found"),
    ],
)
def test_create_order_rejections_do_not_mutate(
    store: Store, overrides: dict[str, Any], error_fragment: str
) -> None:
    args: dict[str, Any] = {
        "customer_name": "Fajar",
        "customer_phone": "081300000001",
        "city": "Yogyakarta",
        "address": "Jl. Kaliurang Km 5",
        "items": [{"sku": "KOK-PTH-L", "qty": 1}],
        "payment_method": "cod",
    }
    args.update(overrides)
    snapshot = store.state.model_dump_json()

    ok, result = call(store, "create_order", **args)

    assert not ok
    assert error_fragment in result["error"]
    assert store.state.model_dump_json() == snapshot


def test_cancel_restores_stock_and_blocks_shipped(store: Store) -> None:
    before = stock(store, "DMR-HTM-M")
    ok, _ = call(store, "cancel_order", order_id="ord-1003")
    assert ok
    assert store.state.orders["ORD-1003"].status == "cancelled"
    assert stock(store, "DMR-HTM-M") == before + 1

    ok, result = call(store, "cancel_order", order_id="ORD-1004")
    assert not ok
    assert "shipped" in result["error"]


def test_return_tool_enforces_only_hard_rules(store: Store) -> None:
    # Hard rule: only delivered orders.
    ok, _ = call(
        store, "request_return", order_id="ORD-1003", sku="DMR-HTM-M", qty=1, reason="size"
    )
    assert not ok
    # Soft rule (policy, not tool): a 14-day-old delivery is accepted by the tool.
    # BazaarBench checks whether the *agent* refuses it.
    ok, _ = call(
        store, "request_return", order_id="ORD-1002", sku="CCS-HTM-32", qty=1, reason="size"
    )
    assert ok


def test_find_orders_by_phone(store: Store) -> None:
    ok, result = call(store, "find_orders", phone="+6281234567801")
    assert ok
    assert {r["order_id"] for r in result} == {"ORD-1001", "ORD-1007"}


def test_bad_arguments_return_readable_errors(store: Store) -> None:
    ok, result = call(store, "create_order", customer_name="X")
    assert not ok
    assert "Invalid arguments" in result["error"]

    outcome = execute(store, ToolCall(id="t", name="nope", arguments={}))
    assert not outcome.ok

    outcome = execute(
        store, ToolCall(id="t", name="get_order", arguments_error="arguments are not valid JSON")
    )
    assert not outcome.ok


def test_tool_specs_have_no_refs() -> None:
    specs = tool_specs()
    assert {s.name for s in specs} >= {"create_order", "handover_to_human"}
    for spec in specs:
        assert "$ref" not in json.dumps(spec.parameters), spec.name
