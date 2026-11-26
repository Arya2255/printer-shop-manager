import pytest

from shop.repository import Repository
from shop.utils import today_jalali


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "shop.db")


def item_named(repository, name):
    return next(item for item in repository.get_state()["inventory_items"] if item["name"] == name)


def test_custom_inventory_item_and_repeated_restocking(repository):
    custom = repository.add_inventory_item(
        {"name": "تراشه کارتریج", "category": "other", "unit": "عدد"}
    )
    repository.restock_item(custom["id"], {"quantity": "۵", "note": "خرید اول"})
    result = repository.restock_item(custom["id"], {"quantity": "2.5", "note": "خرید دوم"})

    assert custom["is_fixed"] is False
    assert result["stock_quantity"] == 7.5
    movements = repository.get_state()["inventory_movements"]
    assert [movement["quantity_change"] for movement in movements] == [5, 2.5]
    assert all(movement["movement_type"] == "restock" for movement in movements)


def test_inventory_name_and_restock_quantity_are_validated(repository):
    with pytest.raises(ValueError, match="نام جنس"):
        repository.add_inventory_item({"name": "", "unit": "عدد"})
    with pytest.raises(ValueError, match="تکراری"):
        repository.add_inventory_item({"name": "کارتریج", "unit": "عدد"})
    cartridge = item_named(repository, "کارتریج")
    with pytest.raises(ValueError, match="تعداد"):
        repository.restock_item(cartridge["id"], {"quantity": 0})


def test_credit_sale_decrements_stock_and_tracks_balance(repository):
    cartridge = item_named(repository, "کارتریج")
    paper = item_named(repository, "کاغذ A4")
    repository.restock_item(cartridge["id"], {"quantity": 5})
    repository.restock_item(paper["id"], {"quantity": 10})

    sale = repository.create_sale(
        {
            "customer_name": "سارا محمدی",
            "customer_phone": "۰۹۳۵۱۲۳۴۵۶۷",
            "relation_type": "دوست",
            "sale_type": "credit",
            "created_at": today_jalali(),
            "due_date": "1405-12-01",
            "items": [
                {"item_id": cartridge["id"], "quantity": 2, "unit_price": 500000},
                {"item_id": paper["id"], "quantity": "۱.۵", "unit_price": 200000},
            ],
            "initial_payment": 300000,
            "note": "باقی ماه بعد",
        }
    )

    assert sale["sale_no"] == 1
    assert sale["total_amount"] == 1300000
    assert sale["paid_amount"] == 300000
    assert sale["remaining_amount"] == 1000000
    assert sale["payment_status"] == "partial"
    assert len(sale["items"]) == 2
    assert sale["items"][0]["item_name"] == "کارتریج"
    assert item_named(repository, "کارتریج")["stock_quantity"] == 3
    assert item_named(repository, "کاغذ A4")["stock_quantity"] == 8.5
    assert repository.get_state()["inventory_movements"][-1]["quantity_change"] == -1.5

    paid = repository.add_payment("sale", sale["id"], {"amount": 1000000})
    assert paid["payment_status"] == "paid"
    assert paid["remaining_amount"] == 0


def test_cash_sale_can_be_walk_in_and_is_fully_paid(repository):
    cable = item_named(repository, "کابل برق پرینتر")
    repository.restock_item(cable["id"], {"quantity": 3})

    sale = repository.create_sale(
        {
            "sale_type": "cash",
            "items": [{"item_id": cable["id"], "quantity": 1, "unit_price": 180000}],
        }
    )

    assert sale["customer_name"] == "مشتری نقدی"
    assert sale["customer_phone"] == ""
    assert sale["total_amount"] == 180000
    assert sale["paid_amount"] == 180000
    assert sale["payment_status"] == "paid"
    assert len(sale["payments"]) == 1


def test_credit_and_installment_sales_require_customer_identity(repository):
    item = item_named(repository, "ریبون")
    repository.restock_item(item["id"], {"quantity": 2})
    payload = {
        "sale_type": "installment",
        "items": [{"item_id": item["id"], "quantity": 1, "unit_price": 100000}],
    }
    with pytest.raises(ValueError, match="نام مشتری"):
        repository.create_sale(payload)
    with pytest.raises(ValueError, match="شماره"):
        repository.create_sale({**payload, "customer_name": "مشتری"})
    with pytest.raises(ValueError, match="رابطه"):
        repository.create_sale(
            {**payload, "customer_name": "مشتری", "customer_phone": "09121112233"}
        )


def test_overselling_rolls_back_entire_sale(repository):
    item = item_named(repository, "کابل دیتای پرینتر")
    repository.restock_item(item["id"], {"quantity": 1})
    revision = repository.get_state()["revision"]

    with pytest.raises(ValueError, match="موجودی"):
        repository.create_sale(
            {
                "sale_type": "cash",
                "items": [{"item_id": item["id"], "quantity": 2, "unit_price": 100000}],
            }
        )

    assert item_named(repository, "کابل دیتای پرینتر")["stock_quantity"] == 1
    assert repository.get_state()["sales"] == []
    assert repository.get_state()["revision"] == revision


def test_sale_requires_at_least_one_valid_item(repository):
    with pytest.raises(ValueError, match="کالا"):
        repository.create_sale({"sale_type": "cash", "items": []})
    with pytest.raises(ValueError, match="جنس"):
        repository.create_sale(
            {
                "sale_type": "cash",
                "items": [{"item_id": 999, "quantity": 1, "unit_price": 1000}],
            }
        )
