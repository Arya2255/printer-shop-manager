from __future__ import annotations

import flet as ft

from .constants import RELATION_TYPES, SALE_TYPES
from .ui_components import (
    MUTED,
    PRIMARY,
    TEXT,
    dialog_shell,
    dropdown_input,
    find_tag,
    info_row,
    panel,
    text_input,
)
from .ui_utils import format_money, format_quantity
from .utils import parse_amount, parse_quantity, today_jalali


class SaleFormMixin:
    def open_sale_form(self) -> ft.AlertDialog:
        items = self.state["inventory_items"]
        options = [
            (
                str(item["id"]),
                f"{item['name']} — موجودی {format_quantity(item['stock_quantity'])} {item['unit']}",
            )
            for item in items
        ]
        lines_column = ft.Column(spacing=10)
        lines: list[dict] = []
        total_preview = ft.Text("جمع فاکتور: ۰ تومان", color=PRIMARY, weight=ft.FontWeight.BOLD)

        customer_name = text_input("نام مشتری", "sale-customer_name")
        customer_phone = text_input(
            "شماره تماس", "sale-customer_phone", keyboard_type=ft.KeyboardType.PHONE
        )
        relation = dropdown_input(
            "نوع رابطه",
            "sale-relation_type",
            "مشتری عادی",
            [(value, value) for value in RELATION_TYPES],
        )
        sale_type = dropdown_input(
            "نوع فروش", "sale-sale_type", "cash", list(SALE_TYPES.items())
        )
        created_at = text_input("تاریخ فروش", "sale-created_at", today_jalali())
        due_date = text_input("موعد تسویه", "sale-due_date")
        initial_payment = text_input(
            "دریافت اولیه",
            "sale-initial_payment",
            0,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        note = text_input("توضیح فاکتور", "sale-note", col={"xs": 12})

        def add_line(_event=None):
            row_index = len(lines)
            item_dropdown = dropdown_input(
                "جنس",
                f"sale-line-item-{row_index}",
                options[0][0] if options else "",
                options,
                col={"xs": 12, "sm": 5},
            )
            quantity = text_input(
                "تعداد",
                f"sale-line-quantity-{row_index}",
                1,
                keyboard_type=ft.KeyboardType.NUMBER,
                col={"xs": 6, "sm": 3},
            )
            price = text_input(
                "قیمت واحد",
                f"sale-line-price-{row_index}",
                0,
                keyboard_type=ft.KeyboardType.NUMBER,
                col={"xs": 6, "sm": 3},
            )
            line = {"item": item_dropdown, "quantity": quantity, "price": price}

            def remove_line(_event=None):
                if line in lines:
                    lines.remove(line)
                    lines_column.controls.remove(row)
                    self.page.update()

            remove = ft.IconButton(
                ft.Icons.DELETE_OUTLINE,
                tooltip="حذف ردیف",
                icon_color="#B91C1C",
                on_click=remove_line,
                col={"xs": 12, "sm": 1},
            )
            row = ft.ResponsiveRow(
                [item_dropdown, quantity, price, remove], spacing=8, run_spacing=8
            )
            lines.append(line)
            lines_column.controls.append(row)
            self.page.update()

        def calculate_total(_event=None):
            try:
                total = sum(
                    int(round(parse_quantity(line["quantity"].value) * parse_amount(line["price"].value)))
                    for line in lines
                )
                total_preview.value = f"جمع فاکتور: {format_money(total)}"
                find_tag(dialog, "sale-error").value = ""
            except ValueError as error:
                find_tag(dialog, "sale-error").value = str(error)
            self.page.update()

        content = ft.Column(
            [
                ft.ResponsiveRow(
                    [
                        sale_type,
                        created_at,
                        customer_name,
                        customer_phone,
                        relation,
                        due_date,
                        initial_payment,
                        note,
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
                ft.Row(
                    [
                        ft.Text("کالاهای فاکتور", weight=ft.FontWeight.BOLD, size=16),
                        ft.TextButton("افزودن ردیف", icon=ft.Icons.ADD, on_click=add_line),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                lines_column,
                ft.Row(
                    [
                        total_preview,
                        ft.TextButton("محاسبه مبلغ", on_click=calculate_total),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    wrap=True,
                ),
            ],
            tight=True,
            spacing=14,
        )

        async def on_save(_event):
            payload = {
                key: find_tag(dialog, f"sale-{key}").value
                for key in (
                    "sale_type",
                    "created_at",
                    "customer_name",
                    "customer_phone",
                    "relation_type",
                    "due_date",
                    "initial_payment",
                    "note",
                )
            }
            payload["items"] = [
                {
                    "item_id": int(line["item"].value),
                    "quantity": line["quantity"].value,
                    "unit_price": line["price"].value,
                }
                for line in lines
                if line["item"].value
            ]
            await self._perform_dialog_save(
                dialog,
                lambda: self.client.create_sale(payload),
                "sale-error",
                "sale-save",
                "فروش ثبت و موجودی انبار به‌روز شد.",
            )

        dialog = dialog_shell(
            "ثبت فروش تازه",
            content,
            save_tag="sale-save",
            save_label="ثبت فروش",
            on_save=on_save,
            on_cancel=self._cancel_dialog,
            error_tag="sale-error",
        )
        self._show_form(dialog)
        add_line()
        return dialog

    def open_sale_details(self, sale_id: int) -> ft.AlertDialog:
        sale = self._owner("sale", sale_id)
        item_controls = [
            info_row(
                item["item_name"],
                f"{format_quantity(item['quantity'])} × {format_money(item['unit_price'])}"
                f" = {format_money(item['line_total'])}",
            )
            for item in sale["items"]
        ]
        payment_controls = [
            info_row(payment["paid_at"], format_money(payment["amount"]))
            for payment in sale["payments"]
        ]
        content = ft.Column(
            [
                info_row("مشتری", sale["customer_name"]),
                info_row("شماره تماس", sale["customer_phone"]),
                info_row("نوع فروش", SALE_TYPES[sale["sale_type"]]),
                info_row("تاریخ", sale["created_at"]),
                info_row("موعد تسویه", sale["due_date"]),
                ft.Divider(),
                ft.Text("کالاها", weight=ft.FontWeight.BOLD),
                *item_controls,
                ft.Divider(),
                ft.Text("دریافت‌ها", weight=ft.FontWeight.BOLD),
                *(payment_controls or [ft.Text("دریافتی ثبت نشده", color=MUTED)]),
                info_row("مبلغ کل", format_money(sale["total_amount"])),
                info_row("دریافت‌شده", format_money(sale["paid_amount"])),
                info_row("مانده", format_money(sale["remaining_amount"])),
                ft.Text(sale["note"], color=MUTED),
            ],
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        )
        dialog = ft.AlertDialog(
            title=ft.Text(f"جزئیات فروش {sale['sale_no']}"),
            content=ft.Container(width=560, content=content),
            actions=[ft.TextButton("بستن", on_click=self._cancel_dialog)],
        )
        self._show_form(dialog)
        return dialog
