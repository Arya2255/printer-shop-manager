from __future__ import annotations

import re
from typing import Any

import jdatetime


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def ascii_digits(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.translate(_PERSIAN_DIGITS).strip()


def parse_amount(value: Any) -> int:
    text = ascii_digits(value).replace("٬", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+", text):
        raise ValueError("مبلغ باید یک عدد صحیح و نامنفی باشد.")
    return int(text)


def parse_quantity(value: Any) -> float:
    text = ascii_digits(value).replace("٫", ".").replace(",", "").replace(" ", "")
    try:
        quantity = float(text)
    except ValueError as exc:
        raise ValueError("تعداد باید یک عدد معتبر باشد.") from exc
    if quantity <= 0:
        raise ValueError("تعداد باید بیشتر از صفر باشد.")
    return quantity


def normalize_phone(value: Any) -> str:
    text = ascii_digits(value)
    text = re.sub(r"[\s\-()]", "", text)
    if not re.fullmatch(r"\+?\d{7,15}", text):
        raise ValueError("شماره تماس معتبر نیست.")
    return text


def normalize_jalali_date(value: Any, *, allow_empty: bool = False) -> str:
    text = ascii_digits(value).replace("/", "-")
    if not text:
        if allow_empty:
            return ""
        raise ValueError("تاریخ را وارد کنید.")
    match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not match:
        raise ValueError("تاریخ باید به شکل سال، ماه و روز باشد.")
    try:
        parsed = jdatetime.date(*(int(part) for part in match.groups()))
    except ValueError as exc:
        raise ValueError("تاریخ واردشده معتبر نیست.") from exc
    return parsed.isoformat()


def today_jalali() -> str:
    return jdatetime.date.today().isoformat()


def payment_summary(total: int, paid: int) -> dict[str, int | str]:
    remaining = max(total - paid, 0)
    if paid >= total:
        status = "paid"
    elif paid > 0:
        status = "partial"
    else:
        status = "unpaid"
    return {
        "paid_amount": paid,
        "remaining_amount": remaining,
        "payment_status": status,
    }
