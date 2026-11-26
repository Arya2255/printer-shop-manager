import jdatetime
import pytest

from shop.utils import (
    normalize_jalali_date,
    normalize_phone,
    parse_amount,
    parse_quantity,
    payment_summary,
    today_jalali,
)


def test_persian_digits_and_separators_are_accepted_for_amounts():
    assert parse_amount("۱۲۳٬۴۵۶") == 123456
    assert parse_amount("12,000") == 12000
    assert parse_amount(" 125000 ") == 125000


def test_amount_must_be_a_non_negative_integer():
    with pytest.raises(ValueError, match="مبلغ"):
        parse_amount("-1")
    with pytest.raises(ValueError, match="مبلغ"):
        parse_amount("12.5")
    with pytest.raises(ValueError, match="مبلغ"):
        parse_amount("")


def test_quantity_supports_decimal_stock_but_rejects_zero():
    assert parse_quantity("۲.۵") == 2.5
    assert parse_quantity("3") == 3.0
    with pytest.raises(ValueError, match="تعداد"):
        parse_quantity("0")


def test_phone_is_normalized_for_android_dialer():
    assert normalize_phone("۰۹۱۲ ۳۴۵ ۶۷۸۹") == "09123456789"
    assert normalize_phone("+98 912 345 6789") == "+989123456789"
    with pytest.raises(ValueError, match="شماره"):
        normalize_phone("123")


def test_jalali_dates_are_normalized_and_validated():
    assert normalize_jalali_date("1404/09/04") == "1404-09-04"
    assert normalize_jalali_date("۱۴۰۴-۹-۴") == "1404-09-04"
    assert normalize_jalali_date("", allow_empty=True) == ""
    with pytest.raises(ValueError, match="تاریخ"):
        normalize_jalali_date("1404-13-01")


def test_today_uses_jalali_calendar():
    assert today_jalali() == jdatetime.date.today().isoformat()


@pytest.mark.parametrize(
    ("total", "paid", "status", "remaining"),
    [
        (100000, 0, "unpaid", 100000),
        (100000, 40000, "partial", 60000),
        (100000, 100000, "paid", 0),
        (0, 0, "paid", 0),
    ],
)
def test_payment_status_is_derived(total, paid, status, remaining):
    assert payment_summary(total, paid) == {
        "paid_amount": paid,
        "remaining_amount": remaining,
        "payment_status": status,
    }
