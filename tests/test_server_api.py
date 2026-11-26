from fastapi.testclient import TestClient
import pytest

from shop.server import create_app
from shop.utils import today_jalali


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "data")


@pytest.fixture
def api(app):
    with TestClient(app) as client:
        yield client


def order_payload():
    return {
        "customer_name": "مشتری آنلاین",
        "customer_phone": "09121112233",
        "received_at": today_jalali(),
        "device_model": "Canon 2900",
        "issue_description": "کاغذ گیر می‌کند",
    }


def test_two_clients_observe_the_same_central_state(api, app):
    second = TestClient(app)
    created = api.post("/api/orders", json=order_payload())

    assert created.status_code == 200, created.text
    first_state = api.get("/api/state").json()
    second_state = second.get("/api/state").json()
    assert first_state["orders"] == second_state["orders"]
    assert first_state["revision"] == second_state["revision"]
    assert second_state["orders"][0]["customer_name"] == "مشتری آنلاین"


def test_order_parts_calls_and_payment_endpoints(api):
    order = api.post("/api/orders", json=order_payload()).json()
    updated = api.put(
        f"/api/orders/{order['id']}", json={"total_cost": 200000, "status": "ready"}
    )
    part = api.post(
        f"/api/orders/{order['id']}/parts", json={"name": "پک کاغذکش", "quantity": 1}
    )
    called = api.post(f"/api/orders/{order['id']}/call", json={"called": True})
    paid = api.post(f"/api/orders/{order['id']}/payments", json={"amount": 75000})

    assert updated.status_code == 200
    assert part.status_code == 200
    assert part.json()["status"] == "needed"
    assert called.json()["customer_called"] is True
    assert paid.json()["paid_amount"] == 75000
    assert paid.json()["payment_status"] == "partial"


def test_inventory_sale_and_restock_endpoints(api):
    item = api.get("/api/state").json()["inventory_items"][0]
    restocked = api.post(f"/api/inventory/{item['id']}/restock", json={"quantity": 4})
    sold = api.post(
        "/api/sales",
        json={
            "sale_type": "cash",
            "items": [{"item_id": item["id"], "quantity": 1, "unit_price": 200000}],
        },
    )

    assert restocked.status_code == 200
    assert sold.status_code == 200, sold.text
    assert sold.json()["payment_status"] == "paid"
    state = api.get("/api/state").json()
    assert state["inventory_items"][0]["stock_quantity"] == 3
    assert len(state["sales"]) == 1


def test_media_upload_streams_to_disk_and_downloads_same_bytes(api):
    order = api.post("/api/orders", json=order_payload()).json()
    content = b"fake-image-content-for-integration"
    uploaded = api.post(
        f"/api/orders/{order['id']}/media?filename=test.jpg",
        content=content,
        headers={"Content-Type": "image/jpeg"},
    )

    assert uploaded.status_code == 200, uploaded.text
    media = uploaded.json()
    downloaded = api.get(media["url"])
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-type"].startswith("image/jpeg")
    assert api.get(f"/api/orders/{order['id']}").json()["media"][0]["size"] == len(content)


def test_validation_errors_are_json_and_do_not_leak_tracebacks(api):
    response = api.post("/api/orders", json={})
    assert response.status_code == 400
    assert response.json() == {"detail": "نام مشتری را وارد کنید."}
    assert "Traceback" not in response.text
