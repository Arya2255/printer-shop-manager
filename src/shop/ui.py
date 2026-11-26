from __future__ import annotations

import asyncio
import flet as ft

from .client import ApiError, HttpClient
from .constants import (
    DEFAULT_INVENTORY_ITEMS,
    ORDER_STATUSES,
    PART_STATUSES,
    SALE_TYPES,
)
from .repository import Repository
from .ui_components import (
    DANGER,
    MUTED,
    PRIMARY,
    TEXT,
    chip,
    dialog_shell,
    dropdown_input,
    empty_state,
    find_tag,
    info_row,
    panel,
    text_input,
)
from .ui_order_forms import OrderFormMixin
from .ui_sales_form import SaleFormMixin
from .ui_utils import dashboard_stats, filter_orders, format_money, format_quantity


class LocalClientAdapter:
    """Wrap Repository with the same method signatures as HttpClient so UI forms
    can always use self.client regardless of local vs network mode."""

    def __init__(self, repository: Repository):
        self._repo = repository

    def get_state(self):
        return self._repo.get_state()

    def create_order(self, payload):
        return self._repo.create_order(payload)

    def get_order(self, order_id):
        return self._repo.get_order(order_id)

    def update_order(self, order_id, payload):
        return self._repo.update_order(order_id, payload)

    def set_order_called(self, order_id, called):
        return self._repo.set_order_called(order_id, called)

    def add_part_request(self, order_id, payload):
        return self._repo.add_part_request(order_id, payload)

    def update_part_request(self, part_id, status):
        return self._repo.update_part_request(part_id, status)

    def add_payment(self, owner_type, owner_id, payload):
        return self._repo.add_payment(owner_type, owner_id, payload)

    def add_inventory_item(self, payload):
        return self._repo.add_inventory_item(payload)

    def restock_item(self, item_id, payload):
        return self._repo.restock_item(item_id, payload)

    def create_sale(self, payload):
        return self._repo.create_sale(payload)

    def get_sale(self, sale_id):
        return self._repo.get_sale(sale_id)

    def upload_media(self, order_id, file_path):
        from pathlib import Path
        size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
        import mimetypes
        mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        return self._repo.add_media(
            order_id,
            {
                "original_name": Path(file_path).name,
                "stored_name": Path(file_path).name,
                "mime_type": mime,
                "size": size,
            },
        )

    def media_url(self, media):
        return media.get("url", "")


class ShopApp(OrderFormMixin, SaleFormMixin):
    def __init__(
        self,
        page: ft.Page,
        repository=None,
        *,
        auto_sync: bool = True,
        base_url: str | None = None,
        auth_token: str | None = None,
    ):
        self.page = page
        self.repository = repository
        self.base_url = base_url or ""
        self.auth_token = auth_token or ""
        self.auto_sync = auto_sync
        self.client: HttpClient | None = None
        self.state: dict = {}
        self.active_dialog: ft.AlertDialog | None = None
        self._media_uploading = False
        self.file_picker = ft.FilePicker(on_result=self._on_media_picked)
        self.url_launcher = ft.UrlLauncher()
        self.body: ft.Control = ft.Container()
        self.nav: ft.NavigationBar | None = None
        page.overlay.extend([self.file_picker, self.url_launcher])
        page.rtl = True
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window.width = 390
        page.window.height = 844
        page.window.title = "مدیر تعمیرگاه پرینتر"
        page.theme = ft.Theme(font_family="Vazirmatn")
        page.fonts = {
            "Vazirmatn": "assets/fonts/Vazirmatn-Regular.ttf",
            "Vazirmatn-Bold": "assets/fonts/Vazirmatn-Bold.ttf",
        }

    async def start(self) -> None:
        if self.repository is not None:
            self.client = LocalClientAdapter(self.repository)
            self.state = self.client.get_state()
        elif self.base_url:
            self.client = HttpClient(self.base_url)
            self.state = self.client.get_state()
        else:
            self.state = {
                "revision": 0,
                "orders": [],
                "inventory_items": DEFAULT_INVENTORY_ITEMS,
                "part_requests": [],
                "sales": [],
                "payments": [],
                "inventory_movements": [],
            }
        self._build_shell()
        self.go("dashboard")

    async def _perform_dialog_save(
        self,
        dialog: ft.AlertDialog,
        operation,
        error_tag: str,
        save_tag: str,
        success_message: str,
    ) -> None:
        error_control = find_tag(dialog, error_tag)
        try:
            if asyncio.iscoroutinefunction(operation):
                result = await operation()
            else:
                result = await asyncio.to_thread(operation)
            self.state = self.client.get_state()
            error_control.value = ""
            self._cancel_dialog()
            self.notify(success_message)
        except ApiError as error:
            error_control.value = str(error)
        except ValueError as error:
            error_control.value = str(error)
        except Exception as error:
            error_control.value = f"خطا: {error}"
        self.page.update()

    def _build_shell(self) -> None:
        self.page.add(self.url_launcher, self.file_picker)
        self.nav = ft.NavigationBar(
            selected_index=0,
            bgcolor=ft.Colors.SURFACE,
            indicator_color=PRIMARY,
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.DASHBOARD, label="داشبورد", selected_icon=ft.Icons.DASHBOARD_ROUNDED
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.PRINT, label="دستگاه‌ها", selected_icon=ft.Icons.PRINT_ROUNDED
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.INVENTORY_2, label="انبار", selected_icon=ft.Icons.INVENTORY_2_OUTLINED
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SHOPPING_CART, label="فروش", selected_icon=ft.Icons.SHOPPING_CART_ROUNDED
                ),
            ],
            on_change=self._navigate,
        )
        self.body = ft.Container(expand=True, padding=10, content=ft.Column([]))
        self.page.add(
            ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(
                                    "تعمیرگاه پرینتر",
                                    size=20,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT,
                                ),
                                ft.FilledButton(
                                    "تازه‌سازی",
                                    icon=ft.Icons.REFRESH,
                                    on_click=lambda _: self.page.run_task(self.refresh()),
                                    bgcolor=PRIMARY,
                                    color=ft.Colors.WHITE,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=10,
                    ),
                    self.body,
                    self.nav,
                ],
                expand=True,
            )
        )

    def _navigate(self, event: ft.ControlEvent) -> None:
        views = ["dashboard", "orders", "inventory", "sales"]
        self.go(views[event.control.selected_index])

    def go(self, view: str, order_id: int | None = None) -> None:
        if view == "dashboard":
            self._render_dashboard()
        elif view == "orders":
            self._render_orders()
        elif view == "orders_detail" and order_id is not None:
            self._render_order_detail(order_id)
        elif view == "inventory":
            self._render_inventory()
        elif view == "sales":
            self._render_sales()
        self.page.update()

    def go_detail(self, order_id: int) -> None:
        self.go("orders_detail", order_id)

    def _cancel_dialog(self, _event=None) -> None:
        if self.active_dialog:
            self.page.pop_dialog()
            self.active_dialog = None
            self.page.update()

    def _show_form(self, dialog: ft.AlertDialog) -> None:
        self.active_dialog = dialog
        self.page.show_dialog(dialog)

    def notify(self, message: str, error: bool = False) -> None:
        self.page.snack_bar = ft.SnackBar(
            ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=DANGER if error else PRIMARY,
            duration=3000,
        )
        self.page.snack_bar.open = True
        self.page.update()

    async def refresh(self, show_loading: bool = True) -> None:
        if show_loading:
            self.body.content = ft.Column(
                [ft.ProgressRing(), ft.Text("در حال به‌روزرسانی…", color=MUTED)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
            self.page.update()
        try:
            if self.repository is not None:
                new_state = self.repository.get_state()
            else:
                assert self.client is not None
                new_state = await asyncio.to_thread(self.client.get_state)
            self.state = new_state
        except ApiError as error:
            self.notify(str(error), error=True)
            return
        if self.nav is not None:
            self.nav.selected_index = 0
        self._render_dashboard()
        self.page.update()

    def _owner(self, owner_type: str, owner_id: int) -> dict:
        key = "orders" if owner_type == "order" else "sales"
        return next(item for item in self.state[key] if item["id"] == owner_id)

    def _item(self, item_id: int) -> dict:
        return next(item for item in self.state["inventory_items"] if item["id"] == item_id)

    def _render_dashboard(self) -> None:
        orders = self.state.get("orders", [])
        sales = self.state.get("sales", [])
        stats = dashboard_stats(orders, sales)

        rows: list[ft.Control] = [
            ft.Row(
                [
                    chip("دستگاه در جریان", PRIMARY),
                    chip(f"{stats['active']} دستگاه", PRIMARY),
                ],
                wrap=True,
            ),
            ft.Row(
                [
                    chip("در انتظار قطعه", "#B45309"),
                    chip(f"{stats['waiting_parts']} دستگاه", "#B45309"),
                ],
                wrap=True,
            ),
            ft.Row(
                [
                    chip("تماس نشده", "#B91C1C"),
                    chip(f"{stats['not_called']} دستگاه", "#B91C1C"),
                ],
                wrap=True,
            ),
            ft.Row(
                [
                    chip("مانده الحصول", "#15803D"),
                    chip(format_money(stats["receivables"]), "#15803D"),
                ],
                wrap=True,
            ),
        ]
        cards = [panel("آمارToday", rows)]
        recent_orders = orders[:8]
        order_cards = [
            panel(
                f"#{o['order_no']} — {o['customer_name']}",
                [
                    info_row("مدل", o["device_model"]),
                    info_row("وضعیت", ORDER_STATUSES[o["status"]]),
                    info_row("تلفن", o["customer_phone"]),
                    info_row("مانده", format_money(o["remaining_amount"])),
                    info_row("تماس", "ثبت شده" if o.get("customer_called") else "ثبت نشده"),
                    ft.Row(
                        [
                            ft.TextButton("مشاهده", on_click=lambda e, oid=o["id"]: self.go_detail(oid)),
                            ft.TextButton("تماس", on_click=lambda e, phone=o["customer_phone"]: self.page.run_task(self.dial_phone(phone))),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
            )
            for o in recent_orders
        ]
        if not order_cards:
            order_cards.append(empty_state("دستگاهی ثبت نشده است."))
        cards.append(panel("آخرین دستگاه‌ها", order_cards))
        self.body.content = ft.Column(cards, spacing=12, expand=True)

    def _render_orders(self) -> None:
        query_control = text_input("جستجو نام، مدل یا تلفن", "orders-search")
        status_dropdown = dropdown_input(
            "وضعیت",
            "orders-status",
            "all",
            [
                ("all", "همه"),
                ("active", "در جریان"),
                ("waiting_parts", "در انتظار قطعه"),
                ("ready", "آماده تحویل"),
                ("delivered", "تحویل شده"),
                ("sent_external", "ارسال شده"),
                ("not_called", "تماس نشده"),
            ],
        )

        def refresh_orders(_event=None):
            orders = filter_orders(
                self.state.get("orders", []),
                status_dropdown.value,
                query_control.value,
            )
            cards = []
            for order in orders:
                cards.append(
                    panel(
                        f"#{order['order_no']} — {order['customer_name']}",
                        [
                            info_row("مدل", order["device_model"]),
                            info_row("وضعیت", ORDER_STATUSES[order["status"]]),
                            info_row("تلفن", order["customer_phone"]),
                            info_row("مانده", format_money(order["remaining_amount"])),
                            info_row("تماس", "ثبت شده" if order.get("customer_called") else "ثبت نشده"),
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "مشاهده",
                                        on_click=lambda e, oid=order["id"]: self.go_detail(oid),
                                    ),
                                    ft.TextButton(
                                        "تماس",
                                        on_click=lambda e, phone=order["customer_phone"]: self.page.run_task(
                                            self.dial_phone(phone)
                                        ),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ]
                    )
                )
            orders_list.content = ft.Column(cards, spacing=10) if cards else empty_state("دستگاه یافت نشد.")
            self.page.update()

        query_control.on_change = refresh_orders
        status_dropdown.on_change = refresh_orders
        toolbar = ft.ResponsiveRow(
            [
                query_control,
                status_dropdown,
                ft.FilledButton(
                    "ثبت دستگاه تازه",
                    icon=ft.Icons.ADD,
                    on_click=lambda _: self.open_order_form(),
                    bgcolor=PRIMARY,
                    color=ft.Colors.WHITE,
                    col={"xs": 12, "sm": 6},
                ),
            ],
            spacing=10,
            run_spacing=10,
        )
        orders_list = ft.Container(expand=True)
        refresh_orders()
        self.body.content = ft.Column([toolbar, ft.Divider(), orders_list], spacing=12, expand=True)

    def _render_order_detail(self, order_id: int) -> None:
        order = next(o for o in self.state["orders"] if o["id"] == order_id)
        part_rows = []
        for part in order.get("part_requests", []):
            status_text = PART_STATUSES[part["status"]]
            color = "#15803D" if part["status"] == "received" else ("#B45309" if part["status"] == "ordered" else "#B91C1C")
            part_rows.append(
                ft.Row(
                    [
                        ft.Text(part["name"], color=TEXT),
                        ft.Text(f"{format_quantity(part['quantity'])} {status_text}", color=color),
                        ft.Row(
                            [
                                ft.TextButton(
                                    "نیاز",
                                    on_click=lambda e, pid=part["id"]: self.page.run_task(self.change_part_status(pid, "needed")),
                                ),
                                ft.TextButton(
                                    "سفارش",
                                    on_click=lambda e, pid=part["id"]: self.page.run_task(self.change_part_status(pid, "ordered")),
                                ),
                                ft.TextButton(
                                    "رسیدگی",
                                    on_click=lambda e, pid=part["id"]: self.page.run_task(self.change_part_status(pid, "received")),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
        media_controls = []
        for media in order.get("media", []):
            media_controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.IMAGE),
                    title=ft.Text(media["original_name"]),
                    subtitle=ft.Text(f"{media['size']} بایت"),
                    trailing=ft.IconButton(
                        ft.Icons.OPEN_IN_NEW,
                        on_click=lambda e, url=media["url"]: self._open_media(url),
                    ),
                )
            )

        async def call_customer(_event=None):
            await self.dial_phone(order["customer_phone"])

        async def mark_called(_event=None):
            await asyncio.to_thread(self.client.set_order_called, order_id, True)
            await self.refresh(show_loading=False)

        async def add_part(_event=None):
            self.open_part_form(order_id)

        async def attach_media(_event=None):
            await self.attach_media(order_id)

        sections = [
            panel(
                "مشتری و دستگاه",
                [
                    info_row("نام", order["customer_name"]),
                    info_row("تلفن", order["customer_phone"]),
                    info_row("تاریخ دریافت", order["received_at"]),
                    info_row("تاریخ وعده", order["promised_at"]),
                    info_row("مدل", order["device_model"]),
                    info_row("کارتریج", order.get("cartridge_type") or "—"),
                    info_row("کابل برق", "دارد" if order.get("power_cable") else "ندارد"),
                    info_row("کابل دیتا", "دارد" if order.get("data_cable") else "ندارد"),
                    info_row("لوازم دیگر", order.get("other_accessories") or "—"),
                    info_row("شرح ایراد", order.get("issue_description") or "—"),
                ],
            ),
            panel(
                "تعمیر و قطعات",
                [
                    info_row("وضعیت", ORDER_STATUSES[order["status"]]),
                    info_row("مرکز ارجاع", order.get("external_center") or "—"),
                    info_row("پیگیری ارجاع", order.get("external_note") or "—"),
                    info_row("خدمات انجام‌شده", order.get("service_description") or "—"),
                    info_row("قطعات مصرف‌شده", order.get("consumed_parts") or "—"),
                    info_row("هزینه کل", format_money(order["total_cost"])),
                    ft.Row(
                        [
                            ft.FilledButton("ثبت قطعه", icon=ft.Icons.ADD, on_click=add_part),
                            ft.FilledButton("ثبت دریافت", icon=ft.Icons.PAYMENT, on_click=lambda _: self.open_payment_form("order", order_id)),
                        ],
                        wrap=True,
                    ),
                    ft.Text("قطعات موردنیاز", weight=ft.FontWeight.BOLD),
                    *part_rows,
                    (ft.FilledButton("افزودن عکس/ویدیو", icon=ft.Icons.ATTACH_FILE, on_click=attach_media) if order.get("media") is not None else ft.Container()),
                ],
            ),
            panel(
                "تماس و دریافت",
                [
                    ft.Row(
                        [
                            ft.FilledButton("تماس با مشتری", icon=ft.Icons.PHONE, on_click=call_customer),
                            ft.FilledButton(
                                "ثبت تماس گرفته شده",
                                icon=ft.Icons.CALL_RECEIVED,
                                bgcolor=PRIMARY,
                                color=ft.Colors.WHITE,
                                on_click=mark_called,
                            ),
                        ],
                        wrap=True,
                    ),
                    info_row("وضعیت تماس", "ثبت شده" if order.get("customer_called") else "ثبت نشده"),
                    info_row("مانده获取", format_money(order["remaining_amount"])),
                    *media_controls,
                ],
            ),
        ]
        self.body.content = ft.Column([ft.Row([ft.Text(f"#{order['order_no']}", size=22, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), *sections], spacing=12, expand=True)

    async def _open_media(self, url: str) -> None:
        if self.base_url and url.startswith("/"):
            full_url = f"{self.base_url}{url}"
        else:
            full_url = url
        await self.url_launcher.launch_url(full_url)

    def _render_inventory(self) -> None:
        items = self.state.get("inventory_items", [])
        cards = []
        for item in items:
            cards.append(
                panel(
                    item["name"],
                    [
                        info_row("واحد", item["unit"]),
                        info_row("موجودی", format_quantity(item["stock_quantity"])),
                        info_row("ثابت", "بله" if item["is_fixed"] else "خیر"),
                        ft.Row(
                            [
                                ft.TextButton("ورود موجودی", on_click=lambda e, iid=item["id"]: self.open_restock_form(iid)),
                                ft.TextButton("افزودن فروش", on_click=lambda e, iid=item["id"]: self._quick_sale(iid)),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ]
                )
            )
        cards.append(
            panel(
                "جنس تازه",
                [
                    ft.FilledButton("ثبت جنس غیرثابت", icon=ft.Icons.ADD, on_click=lambda _: self.open_inventory_form()),
                ],
            )
        )
        self.body.content = ft.Column([ft.Text("انبار و موجودی", size=20, weight=ft.FontWeight.BOLD), *cards], spacing=12, expand=True)

    def _quick_sale(self, item_id: int) -> None:
        item = self._item(item_id)
        sale_payload = {
            "sale_type": "cash",
            "items": [{"item_id": item_id, "quantity": 1, "unit_price": 100000}],
        }
        try:
            self.client.create_sale(sale_payload)
            self.notify("فروش ثبت شد.")
        except ApiError as error:
            self.notify(str(error), error=True)

    def _render_sales(self) -> None:
        sales = self.state.get("sales", [])
        cards = []
        for sale in sales:
            cards.append(
                panel(
                    f"فاکتور {sale['sale_no']} — {sale['customer_name']}",
                    [
                        info_row("نوع", SALE_TYPES[sale["sale_type"]]),
                        info_row("تلفن", sale["customer_phone"] or "—"),
                        info_row("تاریخ", sale["created_at"]),
                        info_row("مبلغ کل", format_money(sale["total_amount"])),
                        info_row("دریافت‌شده", format_money(sale["paid_amount"])),
                        info_row("مانده", format_money(sale["remaining_amount"])),
                        ft.Row(
                            [
                                ft.TextButton("جزئیات", on_click=lambda e, sid=sale["id"]: self.open_sale_details(sid)),
                                ft.TextButton("دریافت", on_click=lambda e, sid=sale["id"]: self.open_payment_form("sale", sid)),
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ]
                )
            )
        if not cards:
            cards.append(empty_state("فروشی ثبت نشده است."))
        cards.append(
            panel(
                "فروش تازه",
                [ft.FilledButton("ثبت فروش", icon=ft.Icons.ADD, on_click=lambda _: self.open_sale_form())],
            )
        )
        self.body.content = ft.Column(cards, spacing=12, expand=True)

    async def dial_phone(self, phone: str) -> None:
        tel_url = f"tel:{phone}"
        await self.url_launcher.launch_url(tel_url)

    async def set_called(self, order_id: int, called: bool) -> None:
        await asyncio.to_thread(self.client.set_order_called, order_id, called)

    async def _on_media_picked(self, event: ft.FilePickerResultEvent) -> None:
        pass
