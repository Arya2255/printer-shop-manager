import asyncio
from types import SimpleNamespace

import flet as ft
import pytest

from shop.repository import Repository
from shop.ui import ShopApp
from shop.utils import today_jalali


class FakePage:
    def __init__(self):
        self.services = []
        self.controls = []
        self.dialogs = []
        self.overlay = []
        self.window = SimpleNamespace(width=390, height=844)
        self.width = 390
        self.height = 844
        self.update_count = 0
        self.client_storage = None

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self, *controls):
        self.update_count += 1

    def show_dialog(self, dialog):
        dialog.open = True
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            dialog = self.dialogs.pop()
            dialog.open = False
            return dialog

    def run_task(self, handler, *args, **kwargs):
        import asyncio
        return asyncio.ensure_future(handler(*args, **kwargs))


class FakeLauncher:
    def __init__(self):
        self.urls = []

    async def launch_url(self, url):
        self.urls.append(url)


def walk(control):
    if control is None or not isinstance(control, ft.Control):
        return
    yield control
    for attribute in ("content", "leading", "title"):
        child = getattr(control, attribute, None)
        if isinstance(child, ft.Control):
            yield from walk(child)
    for attribute in ("controls", "actions"):
        for child in getattr(control, attribute, None) or []:
            yield from walk(child)


def tagged(root, tag):
    return next(control for control in walk(root) if getattr(control, "data", None) == tag)


def texts(root):
    return [control.value for control in walk(root) if isinstance(control, ft.Text)]


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "shop.db")


@pytest.fixture
def app(repository):
    page = FakePage()
    application = ShopApp(page, repository, auto_sync=False)
    asyncio.run(application.start())
    return application


def create_order(repository, **changes):
    payload = {
        "customer_name": "علی رضایی",
        "customer_phone": "09121112233",
        "received_at": today_jalali(),
        "promised_at": "1405-12-01",
        "device_model": "HP 1020",
        "cartridge_type": "12A",
        "power_cable": True,
        "issue_description": "کاغذکش خراب است",
        "total_cost": 300000,
    }
    payload.update(changes)
    return repository.create_order(payload)


def test_all_main_views_and_dialogs_construct_on_phone_width(app, repository):
    order = create_order(repository, status="ready")
    repository.add_part_request(order["id"], {"name": "کاغذکش", "quantity": 1})
    item = repository.get_state()["inventory_items"][0]
    repository.restock_item(item["id"], {"quantity": 5})
    repository.create_sale(
        {
            "sale_type": "cash",
            "items": [{"item_id": item["id"], "quantity": 1, "unit_price": 200000}],
        }
    )
    asyncio.run(app.refresh())

    app.go("dashboard")
    assert "دستگاه در جریان" in texts(app.body)
    app.go("orders")
    assert "HP 1020" in texts(app.body)
    app.go_detail(order["id"])
    assert "قطعات موردنیاز" in texts(app.body)
    assert "تعمیر و قطعات" in texts(app.body)
    app.go("inventory")
    assert "کابل برق پرینتر" in texts(app.body)
    app.go("sales")
    assert "فاکتور 1 — مشتری نقدی" in texts(app.body)

    app.open_order_form()
    assert app.active_dialog is not None
    app.page.pop_dialog()
    app.open_part_form(order["id"])
    app.page.pop_dialog()
    app.open_payment_form("order", order["id"])
    app.page.pop_dialog()
    app.open_inventory_form()
    app.page.pop_dialog()
    app.open_restock_form(item["id"])
    app.page.pop_dialog()
    app.open_sale_form()
    assert tagged(app.active_dialog, "sale-save")


def test_order_form_saves_through_real_repository(app, repository):
    dialog = app.open_order_form()
    values = {
        "order-customer_name": "مشتری تازه",
        "order-customer_phone": "۰۹۱۲۱۱۱۲۲۳۳",
        "order-device_model": "Epson L3150",
        "order-issue_description": "چاپ ندارد",
        "order-cartridge_type": "003",
    }
    for tag, value in values.items():
        tagged(dialog, tag).value = value

    asyncio.run(tagged(dialog, "order-save").on_click(None))

    saved = repository.get_state()["orders"][0]
    assert saved["customer_name"] == "مشتری تازه"
    assert saved["customer_phone"] == "09121112233"
    assert saved["received_at"] == today_jalali()
    assert app.page.dialogs == []


def test_invalid_order_keeps_dialog_open_and_shows_validation(app, repository):
    dialog = app.open_order_form()
    asyncio.run(tagged(dialog, "order-save").on_click(None))

    assert repository.get_state()["orders"] == []
    assert app.active_dialog is dialog
    assert tagged(dialog, "order-error").value == "نام مشتری را وارد کنید."


def test_android_dialer_and_call_registration_are_separate(app, repository):
    order = create_order(repository, status="ready")
    launcher = FakeLauncher()
    app.url_launcher = launcher

    asyncio.run(app.dial_phone(order["customer_phone"]))
    assert launcher.urls == ["tel:09121112233"]
    assert repository.get_order(order["id"])["customer_called"] is False

    asyncio.run(app.set_called(order["id"], True))
    assert repository.get_order(order["id"])["customer_called"] is True
