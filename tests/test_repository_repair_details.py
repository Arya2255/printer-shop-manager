import pytest

from shop.repository import Repository
from shop.utils import today_jalali


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "shop.db")


@pytest.fixture
def order(repository):
    return repository.create_order(
        {
            "customer_name": "رضا کریمی",
            "customer_phone": "09121112233",
            "received_at": today_jalali(),
            "device_model": "Epson L3150",
            "issue_description": "چاپ رنگی ندارد",
        }
    )


def test_part_requests_move_from_needed_to_ordered_and_received(repository, order):
    needed = repository.add_part_request(order["id"], {"name": "کاغذکش", "quantity": "۲"})
    ordered = repository.update_part_request(needed["id"], "ordered")
    received = repository.update_part_request(needed["id"], "received")

    assert needed["status"] == "needed"
    assert needed["quantity"] == 2
    assert needed["ordered_at"] == ""
    assert ordered["ordered_at"]
    assert received["status"] == "received"
    assert received["received_at"]
    assert repository.get_order(order["id"])["part_requests"][0]["name"] == "کاغذکش"
    assert repository.get_state()["part_requests"][0]["order_id"] == order["id"]


def test_part_request_requires_name_and_valid_order(repository, order):
    with pytest.raises(ValueError, match="نام قطعه"):
        repository.add_part_request(order["id"], {"name": "", "quantity": 1})
    with pytest.raises(ValueError, match="دستگاه"):
        repository.add_part_request(999, {"name": "هد", "quantity": 1})


def test_service_consumed_parts_cost_and_payments_are_tracked(repository, order):
    repository.update_order(
        order["id"],
        {
            "service_description": "تمیزکاری هد و سرویس کامل",
            "consumed_parts": "جوهر مشکی و پد فوم",
            "total_cost": "۲۵۰٬۰۰۰",
            "status": "ready",
        },
    )
    repository.add_payment("order", order["id"], {"amount": "۱۰۰٬۰۰۰", "note": "پیش‌پرداخت"})
    result = repository.add_payment("order", order["id"], {"amount": 150000})

    assert result["service_description"] == "تمیزکاری هد و سرویس کامل"
    assert result["consumed_parts"] == "جوهر مشکی و پد فوم"
    assert result["total_cost"] == 250000
    assert result["paid_amount"] == 250000
    assert result["remaining_amount"] == 0
    assert result["payment_status"] == "paid"
    assert len(result["payments"]) == 2
    assert result["payments"][0]["amount"] == 100000
    assert result["payments"][0]["paid_at"] == today_jalali()


def test_partial_and_unpaid_balances_are_derived(repository, order):
    repository.update_order(order["id"], {"total_cost": 300000})
    unpaid = repository.get_order(order["id"])
    partial = repository.add_payment("order", order["id"], {"amount": 125000})

    assert unpaid["payment_status"] == "unpaid"
    assert unpaid["remaining_amount"] == 300000
    assert partial["payment_status"] == "partial"
    assert partial["remaining_amount"] == 175000


def test_invalid_or_excess_payments_are_rejected_without_changing_balance(repository, order):
    repository.update_order(order["id"], {"total_cost": 100000})
    with pytest.raises(ValueError, match="مبلغ"):
        repository.add_payment("order", order["id"], {"amount": 0})
    with pytest.raises(ValueError, match="بیشتر"):
        repository.add_payment("order", order["id"], {"amount": 100001})
    assert repository.get_order(order["id"])["paid_amount"] == 0


def test_cost_cannot_be_negative_or_less_than_existing_payments(repository, order):
    with pytest.raises(ValueError, match="مبلغ"):
        repository.update_order(order["id"], {"total_cost": -1})
    repository.update_order(order["id"], {"total_cost": 100000})
    repository.add_payment("order", order["id"], {"amount": 40000})
    with pytest.raises(ValueError, match="کمتر"):
        repository.update_order(order["id"], {"total_cost": 30000})
