from shop.ui_utils import dashboard_stats, filter_orders, format_money, format_quantity


ORDERS = [
    {
        "id": 1,
        "order_no": 1,
        "customer_name": "علی رضایی",
        "customer_phone": "09121112233",
        "device_model": "HP 1020",
        "status": "waiting_parts",
        "customer_called": False,
        "remaining_amount": 200000,
        "part_requests": [{"status": "needed"}],
    },
    {
        "id": 2,
        "order_no": 2,
        "customer_name": "مریم احمدی",
        "customer_phone": "09351112233",
        "device_model": "Epson L3150",
        "status": "ready",
        "customer_called": False,
        "remaining_amount": 0,
        "part_requests": [],
    },
    {
        "id": 3,
        "order_no": 3,
        "customer_name": "رضا کریمی",
        "customer_phone": "09122223344",
        "device_model": "Canon 2900",
        "status": "delivered",
        "customer_called": True,
        "remaining_amount": 100000,
        "part_requests": [],
    },
]


def test_money_and_quantity_are_readable_in_persian_ui():
    assert format_money(1234567) == "۱٬۲۳۴٬۵۶۷ تومان"
    assert format_quantity(2.0) == "۲"
    assert format_quantity(2.5) == "۲٫۵"


def test_order_filters_cover_workflow_and_unmade_calls():
    assert [o["id"] for o in filter_orders(ORDERS, "active")] == [1, 2]
    assert [o["id"] for o in filter_orders(ORDERS, "waiting_parts")] == [1]
    assert [o["id"] for o in filter_orders(ORDERS, "not_called")] == [2]
    assert [o["id"] for o in filter_orders(ORDERS, "all", "مریم")] == [2]
    assert [o["id"] for o in filter_orders(ORDERS, "all", "1020")] == [1]
    assert [o["id"] for o in filter_orders(ORDERS, "all", "09122223344")] == [3]


def test_dashboard_combines_repair_and_sale_receivables():
    stats = dashboard_stats(ORDERS, [{"remaining_amount": 50000}])
    assert stats == {
        "active": 2,
        "waiting_parts": 1,
        "not_called": 1,
        "receivables": 350000,
    }
