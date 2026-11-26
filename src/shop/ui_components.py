from __future__ import annotations

from typing import Any, Iterable

import flet as ft


PRIMARY = "#155E75"
PRIMARY_DARK = "#164E63"
ACCENT = "#0F766E"
BACKGROUND = "#F1F5F9"
SURFACE = "#FFFFFF"
TEXT = "#0F172A"
MUTED = "#64748B"
BORDER = "#CBD5E1"
WARNING = "#B45309"
DANGER = "#B91C1C"
SUCCESS = "#15803D"


def walk_controls(control: ft.Control | None):
    if control is None or not isinstance(control, ft.Control):
        return
    yield control
    for attribute in ("content", "leading", "title"):
        child = getattr(control, attribute, None)
        if isinstance(child, ft.Control):
            yield from walk_controls(child)
    for attribute in ("controls", "actions"):
        for child in getattr(control, attribute, None) or []:
            yield from walk_controls(child)


def find_tag(control: ft.Control, tag: str) -> ft.Control:
    return next(item for item in walk_controls(control) if getattr(item, "data", None) == tag)


def text_input(
    label: str,
    tag: str,
    value: Any = "",
    *,
    multiline: bool = False,
    keyboard_type: ft.KeyboardType | None = None,
    col: dict[str, int] | None = None,
    **kwargs,
) -> ft.TextField:
    return ft.TextField(
        label=label,
        value="" if value is None else str(value),
        data=tag,
        multiline=multiline,
        min_lines=3 if multiline else None,
        max_lines=5 if multiline else 1,
        keyboard_type=keyboard_type or ft.KeyboardType.TEXT,
        border=ft.OutlineInputBorder(border_radius=10),
        filled=True,
        bgcolor=SURFACE,
        color=TEXT,
        dense=True,
        col=col or {"xs": 12, "sm": 6},
        **kwargs,
    )


def dropdown_input(
    label: str,
    tag: str,
    value: str,
    options: Iterable[tuple[str, str]],
    *,
    col: dict[str, int] | None = None,
    **kwargs,
) -> ft.Dropdown:
    return ft.Dropdown(
        label=label,
        value=value,
        data=tag,
        options=[ft.DropdownOption(key=key, text=label) for key, label in options],
        border=ft.OutlineInputBorder(border_radius=10),
        filled=True,
        bgcolor=SURFACE,
        color=TEXT,
        dense=True,
        col=col or {"xs": 12, "sm": 6},
        **kwargs,
    )


def panel(title: str, controls: list[ft.Control], *, icon=None) -> ft.Card:
    heading = [ft.Icon(icon, color=PRIMARY, size=22)] if icon else []
    heading.append(ft.Text(title, size=17, weight=ft.FontWeight.BOLD, color=TEXT))
    return ft.Card(
        elevation=1,
        bgcolor=SURFACE,
        content=ft.Container(
            padding=16,
            content=ft.Column(
                [ft.Row(heading, spacing=8), ft.Divider(color="#E2E8F0"), *controls],
                spacing=12,
            ),
        ),
    )


def info_row(label: str, value: Any) -> ft.Row:
    return ft.Row(
        [
            ft.Text(label + ":", color=MUTED, size=13),
            ft.Text(str(value or "—"), color=TEXT, size=14, selectable=True, expand=True),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def chip(label: str, color: str = PRIMARY) -> ft.Container:
    return ft.Container(
        content=ft.Text(label, size=12, color=color, weight=ft.FontWeight.BOLD),
        bgcolor=color + "14",
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        border_radius=20,
    )


def empty_state(message: str) -> ft.Container:
    return ft.Container(
        padding=30,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.INBOX_OUTLINED, size=46, color=MUTED),
                ft.Text(message, color=MUTED, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def dialog_shell(
    title: str,
    content: ft.Control,
    *,
    save_tag: str,
    save_label: str,
    on_save,
    on_cancel,
    error_tag: str,
) -> ft.AlertDialog:
    error = ft.Text("", data=error_tag, color=DANGER, size=13)
    save = ft.FilledButton(
        save_label,
        data=save_tag,
        icon=ft.Icons.CHECK,
        bgcolor=PRIMARY,
        color=ft.Colors.WHITE,
        on_click=on_save,
    )
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(title, weight=ft.FontWeight.BOLD),
        content=ft.Container(width=650, content=ft.Column([content, error], tight=True)),
        scrollable=True,
        actions=[
            ft.TextButton("انصراف", on_click=on_cancel),
            save,
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
