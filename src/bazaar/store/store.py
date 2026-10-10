"""Store operations. Hard invariants (stock, existence, voucher validity, COD availability,
cancellable status) are enforced here. Soft business rules (identity verification, return
window, final-sale, return reasons, confirmations) are deliberately left to the agent: following
written policy is exactly what BazaarBench measures.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

from bazaar.store.models import (
    Handover,
    Order,
    OrderItem,
    PaymentMethod,
    Product,
    ReturnReason,
    ReturnRequest,
    ShippingZone,
    StoreState,
    Variant,
)

CANCELLABLE = {"pending_payment", "processing"}


class ToolError(Exception):
    """A business-level failure reported back to the agent (not a crash)."""


@dataclass(frozen=True)
class LineRequest:
    sku: str
    qty: int


def normalize_phone(raw: str) -> str:
    """'+62 812-3456-7801' -> '081234567801'."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    return digits


@lru_cache(maxsize=1)
def _seed_text() -> str:
    return files("bazaar.store").joinpath("seed.json").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def policy_text() -> str:
    return files("bazaar.store").joinpath("policies.md").read_text(encoding="utf-8")


class Store:
    def __init__(self, state: StoreState) -> None:
        self.state = state
        self._sku_index: dict[str, tuple[Product, Variant]] = {
            v.sku: (p, v) for p in state.products.values() for v in p.variants
        }

    @classmethod
    def from_seed(cls) -> Store:
        """A fresh, independent copy of the seed state (ADR-0003)."""
        return cls(StoreState.model_validate_json(_seed_text()))

    # ---------- lookups ----------

    def _variant(self, sku: str) -> tuple[Product, Variant]:
        key = sku.strip().upper()
        if key not in self._sku_index:
            raise ToolError(f"SKU '{sku}' not found")
        return self._sku_index[key]

    def _zone(self, city: str) -> ShippingZone:
        zone = self.state.shipping_zones.get(city.strip().lower())
        if zone is None:
            available = ", ".join(z.city for z in self.state.shipping_zones.values())
            raise ToolError(f"No shipping to '{city}'. Available cities: {available}")
        return zone

    def _order(self, order_id: str) -> Order:
        order = self.state.orders.get(order_id.strip().upper())
        if order is None:
            raise ToolError(f"Order '{order_id}' not found")
        return order

    # ---------- read tools ----------

    def search_products(self, query: str) -> list[dict[str, Any]]:
        tokens = [t for t in re.split(r"\W+", query.lower()) if t]
        scored: list[tuple[int, Product]] = []
        for product in self.state.products.values():
            haystack = " ".join(
                [product.name, product.category, product.description]
                + [v.color for v in product.variants]
            ).lower()
            score = sum(1 for t in tokens if t in haystack)
            if score:
                scored.append((score, product))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [
            {
                "product_id": p.id,
                "name": p.name,
                "price": p.price,
                "final_sale": p.final_sale,
                "colors": sorted({v.color for v in p.variants}),
                "sizes": list(dict.fromkeys(v.size for v in p.variants)),
            }
            for _, p in scored[:5]
        ]

    def get_product(self, product_id: str) -> dict[str, Any]:
        product = self.state.products.get(product_id.strip().upper())
        if product is None:
            raise ToolError(f"Product '{product_id}' not found")
        return product.model_dump(mode="json")

    def calculate_shipping(self, city: str, lines: list[LineRequest]) -> dict[str, Any]:
        zone = self._zone(city)
        grams = sum(self._variant(line.sku)[0].weight_grams * line.qty for line in lines)
        kg = max(1, math.ceil(grams / 1000))
        return {
            "city": zone.city,
            "weight_kg": kg,
            "shipping_fee": kg * zone.fee_per_kg,
            "eta_days": zone.eta_days,
            "cod_available": zone.cod_available,
        }

    def check_voucher(self, code: str, subtotal: int) -> dict[str, Any]:
        voucher_code, discount = self._discount(code, subtotal)
        return {"code": voucher_code, "valid": True, "discount": discount}

    def find_orders(self, phone: str) -> list[dict[str, Any]]:
        wanted = normalize_phone(phone)
        return [
            {
                "order_id": o.id,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
                "total": o.total,
            }
            for o in self.state.orders.values()
            if o.customer_phone == wanted
        ]

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._order(order_id).model_dump(mode="json")

    # ---------- write tools ----------

    def create_order(
        self,
        *,
        customer_name: str,
        customer_phone: str,
        city: str,
        address: str,
        lines: list[LineRequest],
        payment_method: PaymentMethod,
        voucher_code: str | None = None,
    ) -> dict[str, Any]:
        if not lines:
            raise ToolError("Order must contain at least one item")
        zone = self._zone(city)
        if payment_method == "cod" and not zone.cod_available:
            raise ToolError(f"COD is not available for {zone.city}")

        merged: dict[str, int] = {}
        for line in lines:
            key = self._variant(line.sku)[1].sku
            merged[key] = merged.get(key, 0) + line.qty

        items: list[OrderItem] = []
        for sku, qty in merged.items():
            product, variant = self._variant(sku)
            if qty > 20:
                raise ToolError(f"Max 20 pcs per variant; {sku} requested {qty}")
            if variant.stock < qty:
                raise ToolError(
                    f"Insufficient stock for {sku}: requested {qty}, available {variant.stock}"
                )
            items.append(
                OrderItem(
                    sku=sku,
                    product_id=product.id,
                    name=product.name,
                    size=variant.size,
                    color=variant.color,
                    qty=qty,
                    unit_price=product.price,
                )
            )

        subtotal = sum(i.unit_price * i.qty for i in items)
        code, discount = self._discount(voucher_code, subtotal) if voucher_code else (None, 0)
        shipping = self.calculate_shipping(zone.city, [LineRequest(i.sku, i.qty) for i in items])

        # All checks passed: now mutate.
        for item in items:
            self._variant(item.sku)[1].stock -= item.qty
        order_id = f"ORD-{self.state.next_order_number}"
        self.state.next_order_number += 1
        order = Order(
            id=order_id,
            customer_name=customer_name.strip(),
            customer_phone=normalize_phone(customer_phone),
            city=zone.city,
            address=address.strip(),
            payment_method=payment_method,
            status="pending_payment" if payment_method == "transfer" else "processing",
            items=items,
            subtotal=subtotal,
            discount=discount,
            shipping_fee=shipping["shipping_fee"],
            total=subtotal - discount + shipping["shipping_fee"],
            voucher_code=code,
            created_at=self.state.today,
        )
        self.state.orders[order_id] = order
        return order.model_dump(mode="json")

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        order = self._order(order_id)
        if order.status not in CANCELLABLE:
            raise ToolError(f"Order {order.id} has status '{order.status}' and cannot be cancelled")
        for item in order.items:
            self._variant(item.sku)[1].stock += item.qty
        order.status = "cancelled"
        return {"order_id": order.id, "status": order.status}

    def request_return(
        self, order_id: str, sku: str, qty: int, reason: ReturnReason
    ) -> dict[str, Any]:
        order = self._order(order_id)
        if order.status != "delivered":
            raise ToolError(f"Order {order.id} has status '{order.status}'; only delivered orders")
        line = next((i for i in order.items if i.sku == sku.strip().upper()), None)
        if line is None:
            raise ToolError(f"SKU '{sku}' is not in order {order.id}")
        already = sum(r.qty for r in order.returns if r.sku == line.sku)
        if qty + already > line.qty:
            raise ToolError(f"Return qty exceeds purchased qty for {line.sku}")
        order.returns.append(
            ReturnRequest(sku=line.sku, qty=qty, reason=reason, requested_at=self.state.today)
        )
        return {"order_id": order.id, "sku": line.sku, "qty": qty, "status": "requested"}

    def handover_to_human(self, reason: str, summary: str) -> dict[str, Any]:
        self.state.handovers.append(Handover(reason=reason.strip(), summary=summary.strip()))
        return {"status": "handed_over", "message": "A human admin will continue this chat."}

    # ---------- helpers ----------

    def _discount(self, code: str | None, subtotal: int) -> tuple[str | None, int]:
        if not code:
            return None, 0
        voucher = self.state.vouchers.get(code.strip().upper())
        if voucher is None:
            raise ToolError(f"Voucher '{code}' does not exist")
        if voucher.valid_until < self.state.today:
            raise ToolError(f"Voucher {voucher.code} expired on {voucher.valid_until.isoformat()}")
        if subtotal < voucher.min_subtotal:
            raise ToolError(
                f"Voucher {voucher.code} needs a minimum subtotal of {voucher.min_subtotal}; "
                f"current subtotal is {subtotal}"
            )
        percent = voucher.kind == "percent"
        discount = subtotal * voucher.value // 100 if percent else voucher.value
        if voucher.max_discount is not None:
            discount = min(discount, voucher.max_discount)
        return voucher.code, min(discount, subtotal)
