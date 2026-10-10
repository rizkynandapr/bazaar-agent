"""Domain model of the fictional store. All money is integer Rupiah (IDR)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PaymentMethod = Literal["cod", "transfer"]
OrderStatus = Literal["pending_payment", "processing", "shipped", "delivered", "cancelled"]
ReturnReason = Literal["size", "defect", "wrong_item", "changed_mind"]


class Variant(BaseModel):
    sku: str
    size: str
    color: str
    stock: int = Field(ge=0)


class Product(BaseModel):
    id: str
    name: str
    category: str
    price: int = Field(gt=0)
    weight_grams: int = Field(gt=0)
    final_sale: bool = False
    description: str
    variants: list[Variant]


class ShippingZone(BaseModel):
    city: str
    fee_per_kg: int = Field(gt=0)
    eta_days: int = Field(gt=0)
    cod_available: bool


class Voucher(BaseModel):
    code: str
    kind: Literal["percent", "fixed"]
    value: int = Field(gt=0)
    min_subtotal: int = Field(default=0, ge=0)
    max_discount: int | None = None
    valid_until: date


class OrderItem(BaseModel):
    sku: str
    product_id: str
    name: str
    size: str
    color: str
    qty: int = Field(ge=1)
    unit_price: int = Field(gt=0)


class ReturnRequest(BaseModel):
    sku: str
    qty: int = Field(ge=1)
    reason: ReturnReason
    status: Literal["requested"] = "requested"
    requested_at: date


class Order(BaseModel):
    id: str
    customer_name: str
    customer_phone: str
    city: str
    address: str
    payment_method: PaymentMethod
    status: OrderStatus
    items: list[OrderItem]
    subtotal: int
    discount: int = 0
    shipping_fee: int
    total: int
    voucher_code: str | None = None
    created_at: date
    delivered_at: date | None = None
    returns: list[ReturnRequest] = Field(default_factory=list)


class Handover(BaseModel):
    reason: str
    summary: str


class StoreState(BaseModel):
    """Everything the agent can read or change. Graded by comparing final vs expected state."""

    store_name: str
    today: date
    products: dict[str, Product]
    shipping_zones: dict[str, ShippingZone]  # keyed by lower-case city name
    vouchers: dict[str, Voucher]  # keyed by upper-case code
    orders: dict[str, Order]
    handovers: list[Handover] = Field(default_factory=list)
    next_order_number: int
