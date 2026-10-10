"""Tool registry: argument schemas, descriptions, and a single safe dispatch function.

The same ``execute`` path is used by the agent at runtime and by BazaarBench when it replays a
task's expected actions, so the grader and the agent can never disagree about what a tool does.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from bazaar.llm import ToolCall, ToolSpec
from bazaar.store.models import PaymentMethod, ReturnReason
from bazaar.store.store import LineRequest, Store, ToolError

# ---------- argument models ----------


class SearchProductsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=100, description="Keywords, e.g. 'kemeja linen'")


class GetProductArgs(BaseModel):
    product_id: str = Field(description="Product id from search_products, e.g. 'P01'")


class LineItem(BaseModel):
    sku: str = Field(description="Variant SKU, e.g. 'KLP-PTH-M'")
    qty: int = Field(ge=1, le=20)


class CalculateShippingArgs(BaseModel):
    city: str
    items: list[LineItem] = Field(min_length=1)


class CheckVoucherArgs(BaseModel):
    code: str
    subtotal: int = Field(ge=0, description="Order subtotal in IDR before discount")


class FindOrdersArgs(BaseModel):
    phone: str = Field(description="Customer phone number")


class OrderIdArgs(BaseModel):
    order_id: str = Field(description="Order id, e.g. 'ORD-1001'")


class CreateOrderArgs(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=8, max_length=20)
    city: str
    address: str = Field(min_length=5, max_length=300)
    items: list[LineItem] = Field(min_length=1)
    payment_method: PaymentMethod
    voucher_code: str | None = None


class RequestReturnArgs(BaseModel):
    order_id: str
    sku: str
    qty: int = Field(ge=1, le=20)
    reason: ReturnReason


class HandoverArgs(BaseModel):
    reason: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1000, description="Short summary for the admin")


# ---------- registry ----------


def _lines(items: list[LineItem]) -> list[LineRequest]:
    return [LineRequest(i.sku, i.qty) for i in items]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable[[Store, Any], Any]
    writes: bool = False


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "search_products",
            "Search the catalog by keywords. Returns products with price, colors and sizes.",
            SearchProductsArgs,
            lambda s, a: s.search_products(a.query),
        ),
        Tool(
            "get_product",
            "Get one product with every variant (SKU, size, color, current stock).",
            GetProductArgs,
            lambda s, a: s.get_product(a.product_id),
        ),
        Tool(
            "calculate_shipping",
            "Shipping fee, ETA and COD availability for a city and a list of items.",
            CalculateShippingArgs,
            lambda s, a: s.calculate_shipping(a.city, _lines(a.items)),
        ),
        Tool(
            "check_voucher",
            "Validate a voucher code for a subtotal and return the discount in IDR.",
            CheckVoucherArgs,
            lambda s, a: s.check_voucher(a.code, a.subtotal),
        ),
        Tool(
            "find_orders",
            "List orders registered to a phone number.",
            FindOrdersArgs,
            lambda s, a: s.find_orders(a.phone),
        ),
        Tool(
            "get_order",
            "Get full order details, including the phone number registered to it.",
            OrderIdArgs,
            lambda s, a: s.get_order(a.order_id),
        ),
        Tool(
            "create_order",
            "Create an order. Computes subtotal, discount, shipping and total. "
            "Only call after the customer explicitly confirms the summary.",
            CreateOrderArgs,
            lambda s, a: s.create_order(
                customer_name=a.customer_name,
                customer_phone=a.customer_phone,
                city=a.city,
                address=a.address,
                lines=_lines(a.items),
                payment_method=a.payment_method,
                voucher_code=a.voucher_code,
            ),
            writes=True,
        ),
        Tool(
            "cancel_order",
            "Cancel an order. Only call after the customer explicitly confirms.",
            OrderIdArgs,
            lambda s, a: s.cancel_order(a.order_id),
            writes=True,
        ),
        Tool(
            "request_return",
            "File a return request for an item in a delivered order. "
            "Only call after the customer explicitly confirms.",
            RequestReturnArgs,
            lambda s, a: s.request_return(a.order_id, a.sku, a.qty, a.reason),
            writes=True,
        ),
        Tool(
            "handover_to_human",
            "Transfer the conversation to a human admin. Ends the agent's part of the chat.",
            HandoverArgs,
            lambda s, a: s.handover_to_human(a.reason, a.summary),
            writes=True,
        ),
    ]
}

HANDOVER_TOOL = "handover_to_human"


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline ``$defs`` references: some OpenAI-compatible providers reject ``$ref``."""
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    resolved: dict[str, Any] = resolve(schema)
    return resolved


def tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name=t.name,
            description=t.description,
            parameters=_inline_refs(t.args_model.model_json_schema()),
        )
        for t in TOOLS.values()
    ]


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    content: str  # JSON string handed back to the model


def _error(message: str) -> ToolOutcome:
    return ToolOutcome(ok=False, content=json.dumps({"error": message}, ensure_ascii=False))


def execute(store: Store, call: ToolCall) -> ToolOutcome:
    """Run one tool call. Never raises for bad input; returns an error the model can read."""
    tool = TOOLS.get(call.name)
    if tool is None:
        return _error(f"Unknown tool '{call.name}'")
    if call.arguments_error:
        return _error(call.arguments_error)
    try:
        args = tool.args_model.model_validate(call.arguments)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
        )
        return _error(f"Invalid arguments: {problems}")
    try:
        result = tool.run(store, args)
    except ToolError as exc:
        return _error(str(exc))
    return ToolOutcome(ok=True, content=json.dumps(result, ensure_ascii=False, default=str))
