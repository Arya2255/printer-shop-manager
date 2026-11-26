from __future__ import annotations

from typing import Any

from .utils import ascii_digits


_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def format_money(value: int | float) -> str:
    return f"{int(value):,}".replace(",", "٬").translate(_PERSIAN_DIGITS) + " تومان"


def format_quantity(value: int | float) -> str:
    number = float(value)
    text = str(int(number)) if number.is_integer() else f"{number:g}".replace(".", "٫")
    return text.translate(_PERSIAN_DIGITS)


def filter_orders(
    orders: list[dict[str, Any]], status_filter: str = "all", search: str = ""
) -> list[dict[str, Any]]:
    result = orders
    if status_filter == "active":
        result = [order for order in result if order["status"] not in {"delivered", "cancelled"}]
    elif status_filter == "not_called":
        result = [
            order
            for order in result
            if order["status"] == "ready" and not order.get("customer_called")
        ]
    elif status_filter != "all":
        result = [order for order in result if order["status"] == status_filter]
    query = search.strip().casefold()
    if query:
        latin_query = ascii_digits(query)
        result = [
            order
            for order in result
            if any(
                query in str(order.get(field, "")).casefold()
                or latin_query in ascii_digits(order.get(field, ""))
                for field in ("order_no", "customer_name", "customer_phone", "device_model")
            )
        ]
    return result


def dashboard_stats(
    orders: list[dict[str, Any]], sales: list[dict[str, Any]]
) -> dict[str, int]:
    return {
        "active": len(
            [order for order in orders if order["status"] not in {"delivered", "cancelled"}]
        ),
        "waiting_parts": len([order for order in orders if order["status"] == "waiting_parts"]),
        "not_called": len(
            [
                order
                for order in orders
                if order["status"] == "ready" and not order.get("customer_called")
            ]
        ),
        "receivables": sum(order["remaining_amount"] for order in orders)
        + sum(sale["remaining_amount"] for sale in sales),
    }
