import pytest

from shop.repository import Repository
from shop.utils import today_jalali


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "shop.db")


def order_payload(**changes):
    payload = {
        "customer_name": "علی رضایی",
        "customer_phone": "۰۹۱۲۳۴۵۶۷۸۹",
        "received_at": today_jalali(),
        "promised_at": "1405-10-10",
        "device_model": "HP LaserJet 1020",
        "cartridge_type": "12A",
        "power_cable": True,
        "data_cable": False,
        "other_accessories": "کیف دستگاه",
        "issue_description": "کاغذکش خراب است",
    }
    payload.update(changes)
    return payload


def test_repository_seeds_fixed_inventory_and_creates_numbered_order(repository):
    state = repository.get_state()
    assert [item["name"] for item in state["inventory_items"]] == [
        "کارتریج",
        "کابل برق پرینتر",
        "کابل دیتای پرینتر",
        "کاغذ A4",
        "جوهر اپسون",
        "ریبون",
    ]
    assert all(item["stock_quantity"] == 0 for item in state["inventory_items"])

    first = repository.create_order(order_payload())
    second = repository.create_order(order_payload(customer_name="مریم احمدی"))

    assert first["order_no"] == 1
    assert second["order_no"] == 2
    assert first["customer_phone"] == "09123456789"
    assert first["status"] == "received"
    assert first["customer_called"] is False
    assert first["paid_amount"] == 0
    assert first["remaining_amount"] == 0
    assert first["payment_status"] == "paid"
    assert first["part_requests"] == []
    assert first["media"] == []
    assert repository.get_state()["revision"] > state["revision"]


def test_required_order_fields_and_status_are_validated(repository):
    with pytest.raises(ValueError, match="نام مشتری"):
        repository.create_order(order_payload(customer_name=" "))
    with pytest.raises(ValueError, match="مدل دستگاه"):
        repository.create_order(order_payload(device_model=""))
    with pytest.raises(ValueError, match="شرح ایراد"):
        repository.create_order(order_payload(issue_description=""))
    with pytest.raises(ValueError, match="تاریخ"):
        repository.create_order(order_payload(received_at="1405-99-99"))


def test_external_repair_and_call_tracking_are_saved(repository):
    order = repository.create_order(order_payload())

    updated = repository.update_order(
        order["id"],
        {
            "status": "sent_external",
            "external_center": "تعمیرگاه مرکزی شیراز",
            "external_note": "تعمیر برد",
        },
    )
    called = repository.set_order_called(order["id"], True)
    cleared = repository.set_order_called(order["id"], False)

    assert updated["status"] == "sent_external"
    assert updated["external_center"] == "تعمیرگاه مرکزی شیراز"
    assert called["customer_called"] is True
    assert called["called_at"]
    assert cleared["customer_called"] is False
    assert cleared["called_at"] == ""


def test_external_repair_requires_destination(repository):
    order = repository.create_order(order_payload())
    with pytest.raises(ValueError, match="مرکز"):
        repository.update_order(order["id"], {"status": "sent_external"})
