from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile

import flet as ft

from .constants import ORDER_STATUSES, PART_STATUSES
from .ui_components import (
    DANGER,
    PRIMARY,
    dialog_shell,
    dropdown_input,
    find_tag,
    panel,
    text_input,
)
from .ui_utils import format_money
from .utils import today_jalali


class OrderFormMixin:
    def open_order_form(self, order: dict | None = None) -> ft.AlertDialog:
        existing = order or {}
        fields = [
            text_input("نام مشتری", "order-customer_name", existing.get("customer_name", "")),
            text_input(
                "شماره تماس",
                "order-customer_phone",
                existing.get("customer_phone", ""),
                keyboard_type=ft.KeyboardType.PHONE,
            ),
            text_input(
                "تاریخ دریافت",
                "order-received_at",
                existing.get("received_at", today_jalali()),
            ),
            text_input(
                "تاریخ وعده تحویل",
                "order-promised_at",
                existing.get("promised_at", ""),
            ),
            text_input("مدل دستگاه", "order-device_model", existing.get("device_model", "")),
            text_input("نوع کارتریج", "order-cartridge_type", existing.get("cartridge_type", "")),
            dropdown_input(
                "وضعیت دستگاه",
                "order-status",
                existing.get("status", "received"),
                list(ORDER_STATUSES.items()),
            ),
            text_input(
                "مرکز تعمیرات مقصد",
                "order-external_center",
                existing.get("external_center", ""),
                hint_text="فقط در صورت ارسال به تعمیرگاه دیگر",
            ),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Checkbox(
                            label="کابل برق همراه دستگاه است",
                            value=existing.get("power_cable", False),
                            data="order-power_cable",
                        ),
                        ft.Checkbox(
                            label="کابل اتصال به کامپیوتر همراه است",
                            value=existing.get("data_cable", False),
                            data="order-data_cable",
                        ),
                    ],
                    wrap=True,
                ),
                col={"xs": 12},
            ),
            text_input(
                "سایر لوازم همراه",
                "order-other_accessories",
                existing.get("other_accessories", ""),
                col={"xs": 12},
            ),
            text_input(
                "شرح ایراد از زبان مشتری",
                "order-issue_description",
                existing.get("issue_description", ""),
                multiline=True,
                col={"xs": 12},
            ),
            text_input(
                "توضیح ارجاع یا پیگیری",
                "order-external_note",
                existing.get("external_note", ""),
                multiline=True,
                col={"xs": 12},
            ),
            text_input(
                "خدمات و سرویس انجام‌شده",
                "order-service_description",
                existing.get("service_description", ""),
                multiline=True,
                col={"xs": 12},
            ),
            text_input(
                "قطعات مصرف‌شده",
                "order-consumed_parts",
                existing.get("consumed_parts", ""),
                multiline=True,
                col={"xs": 12},
            ),
            text_input(
                "هزینه کل به تومان",
                "order-total_cost",
                existing.get("total_cost", 0),
                keyboard_type=ft.KeyboardType.NUMBER,
            ),
            text_input("یادداشت", "order-notes", existing.get("notes", ""), col={"xs": 12}),
        ]
        content = ft.ResponsiveRow(fields, spacing=12, run_spacing=12)

        async def on_save(event):
            payload = {
                key: find_tag(dialog, f"order-{key}").value
                for key in (
                    "customer_name",
                    "customer_phone",
                    "received_at",
                    "promised_at",
                    "device_model",
                    "cartridge_type",
                    "status",
                    "external_center",
                    "other_accessories",
                    "issue_description",
                    "external_note",
                    "service_description",
                    "consumed_parts",
                    "total_cost",
                    "notes",
                )
            }
            payload["power_cable"] = find_tag(dialog, "order-power_cable").value
            payload["data_cable"] = find_tag(dialog, "order-data_cable").value
            if existing:
                operation = lambda: self.client.update_order(existing["id"], payload)
                message = "تغییرات دستگاه ذخیره شد."
            else:
                operation = lambda: self.client.create_order(payload)
                message = "دستگاه تازه ثبت شد."
            await self._perform_dialog_save(
                dialog, operation, "order-error", "order-save", message
            )

        dialog = dialog_shell(
            "ویرایش دستگاه" if existing else "ثبت دستگاه تازه",
            content,
            save_tag="order-save",
            save_label="ذخیره",
            on_save=on_save,
            on_cancel=self._cancel_dialog,
            error_tag="order-error",
        )
        self._show_form(dialog)
        return dialog

    def open_part_form(self, order_id: int) -> ft.AlertDialog:
        content = ft.ResponsiveRow(
            [
                text_input("نام قطعه", "part-name", col={"xs": 12, "sm": 6}),
                text_input(
                    "تعداد",
                    "part-quantity",
                    1,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    col={"xs": 12, "sm": 6},
                ),
                dropdown_input(
                    "وضعیت",
                    "part-status",
                    "needed",
                    list(PART_STATUSES.items()),
                ),
                text_input("توضیح", "part-note", col={"xs": 12}),
            ],
            spacing=12,
            run_spacing=12,
        )

        async def on_save(_event):
            payload = {
                "name": find_tag(dialog, "part-name").value,
                "quantity": find_tag(dialog, "part-quantity").value,
                "status": find_tag(dialog, "part-status").value,
                "note": find_tag(dialog, "part-note").value,
            }
            await self._perform_dialog_save(
                dialog,
                lambda: self.client.add_part_request(order_id, payload),
                "part-error",
                "part-save",
                "قطعه موردنیاز ثبت شد.",
            )

        dialog = dialog_shell(
            "افزودن قطعه موردنیاز",
            content,
            save_tag="part-save",
            save_label="ثبت قطعه",
            on_save=on_save,
            on_cancel=self._cancel_dialog,
            error_tag="part-error",
        )
        self._show_form(dialog)
        return dialog

    async def change_part_status(self, part_id: int, status: str) -> None:
        try:
            await asyncio.to_thread(self.client.update_part_request, part_id, status)
            await self.refresh(show_loading=False)
            self.notify("وضعیت قطعه تغییر کرد.")
        except Exception as error:
            self.notify(str(error), error=True)

    def open_payment_form(self, owner_type: str, owner_id: int) -> ft.AlertDialog:
        owner = self._owner(owner_type, owner_id)
        remaining = owner["remaining_amount"]
        content = ft.Column(
            [
                ft.Text(f"مانده فعلی: {format_money(remaining)}", color=PRIMARY),
                ft.ResponsiveRow(
                    [
                        text_input(
                            "مبلغ دریافت به تومان",
                            "payment-amount",
                            remaining,
                            keyboard_type=ft.KeyboardType.NUMBER,
                            col={"xs": 12},
                        ),
                        text_input(
                            "تاریخ دریافت",
                            "payment-paid_at",
                            today_jalali(),
                            col={"xs": 12},
                        ),
                        text_input("توضیح", "payment-note", col={"xs": 12}),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
            ],
            tight=True,
        )

        async def on_save(_event):
            payload = {
                "amount": find_tag(dialog, "payment-amount").value,
                "paid_at": find_tag(dialog, "payment-paid_at").value,
                "note": find_tag(dialog, "payment-note").value,
            }
            await self._perform_dialog_save(
                dialog,
                lambda: self.client.add_payment(owner_type, owner_id, payload),
                "payment-error",
                "payment-save",
                "دریافت ثبت شد.",
            )

        dialog = dialog_shell(
            "ثبت دریافت",
            content,
            save_tag="payment-save",
            save_label="ثبت دریافت",
            on_save=on_save,
            on_cancel=self._cancel_dialog,
            error_tag="payment-error",
        )
        self._show_form(dialog)
        return dialog

    def open_inventory_form(self) -> ft.AlertDialog:
        content = ft.ResponsiveRow(
            [
                text_input("نام جنس", "inventory-name", col={"xs": 12}),
                text_input("واحد شمارش", "inventory-unit", "عدد"),
                text_input("دسته", "inventory-category", "other"),
                text_input("توضیح", "inventory-notes", col={"xs": 12}),
            ],
            spacing=12,
            run_spacing=12,
        )

        async def on_save(_event):
            payload = {
                key: find_tag(dialog, f"inventory-{key}").value
                for key in ("name", "unit", "category", "notes")
            }
            await self._perform_dialog_save(
                dialog,
                lambda: self.client.add_inventory_item(payload),
                "inventory-error",
                "inventory-save",
                "جنس تازه به انبار اضافه شد.",
            )

        dialog = dialog_shell(
            "افزودن جنس غیرثابت",
            content,
            save_tag="inventory-save",
            save_label="ذخیره جنس",
            on_save=on_save,
            on_cancel=self._cancel_dialog,
            error_tag="inventory-error",
        )
        self._show_form(dialog)
        return dialog

    def open_restock_form(self, item_id: int) -> ft.AlertDialog:
        item = self._item(item_id)
        content = ft.Column(
            [
                ft.Text(item["name"], weight=ft.FontWeight.BOLD, size=16),
                ft.ResponsiveRow(
                    [
                        text_input(
                            f"تعداد ورود بر حسب {item['unit']}",
                            "restock-quantity",
                            keyboard_type=ft.KeyboardType.NUMBER,
                            col={"xs": 12},
                        ),
                        text_input("توضیح خرید", "restock-note", col={"xs": 12}),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
            ],
            tight=True,
        )

        async def on_save(_event):
            payload = {
                "quantity": find_tag(dialog, "restock-quantity").value,
                "note": find_tag(dialog, "restock-note").value,
            }
            await self._perform_dialog_save(
                dialog,
                lambda: self.client.restock_item(item_id, payload),
                "restock-error",
                "restock-save",
                "ورود جنس به انبار ثبت شد.",
            )

        dialog = dialog_shell(
            "ورود موجودی به انبار",
            content,
            save_tag="restock-save",
            save_label="ثبت ورود",
            on_save=on_save,
            on_cancel=self._cancel_dialog,
            error_tag="restock-error",
        )
        self._show_form(dialog)
        return dialog

    async def attach_media(self, order_id: int) -> None:
        if self._media_uploading:
            return
        files = await self.file_picker.pick_files(
            dialog_title="انتخاب عکس یا ویدیو",
            file_type=ft.FilePickerFileType.MEDIA,
            allow_multiple=True,
            with_data=False,
        )
        if not files:
            return
        self._media_uploading = True
        uploaded = 0
        try:
            for selected in files:
                path = selected.path
                temporary = None
                if not path and selected.bytes:
                    suffix = Path(selected.name).suffix
                    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                    handle.write(selected.bytes)
                    handle.close()
                    temporary = Path(handle.name)
                    path = str(temporary)
                if not path:
                    raise RuntimeError(
                        "مسیر فایل انتخاب‌شده در دسترس نیست. روی گوشی دوباره انتخاب کنید."
                    )
                try:
                    await asyncio.to_thread(self.client.upload_media, order_id, path)
                    uploaded += 1
                finally:
                    if temporary:
                        temporary.unlink(missing_ok=True)
            await self.refresh(show_loading=False)
            self.notify(f"{uploaded} فایل رسانه بارگذاری شد.")
        except Exception as error:
            if uploaded:
                await self.refresh(show_loading=False)
            self.notify(str(error), error=True)
        finally:
            self._media_uploading = False
