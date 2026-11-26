from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import DEFAULT_INVENTORY_ITEMS, ORDER_STATUSES, PART_STATUSES, SALE_TYPES
from .utils import (
    normalize_jalali_date,
    normalize_phone,
    parse_amount,
    parse_quantity,
    payment_summary,
    today_jalali,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT INTO meta(key, value) VALUES ('revision', '0')
                    ON CONFLICT(key) DO NOTHING;

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    promised_at TEXT NOT NULL DEFAULT '',
                    device_model TEXT NOT NULL,
                    cartridge_type TEXT NOT NULL DEFAULT '',
                    power_cable INTEGER NOT NULL DEFAULT 0,
                    data_cable INTEGER NOT NULL DEFAULT 0,
                    other_accessories TEXT NOT NULL DEFAULT '',
                    issue_description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'received',
                    external_center TEXT NOT NULL DEFAULT '',
                    external_note TEXT NOT NULL DEFAULT '',
                    customer_called INTEGER NOT NULL DEFAULT 0,
                    called_at TEXT NOT NULL DEFAULT '',
                    service_description TEXT NOT NULL DEFAULT '',
                    consumed_parts TEXT NOT NULL DEFAULT '',
                    total_cost INTEGER NOT NULL DEFAULT 0,
                    delivered_at TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    size INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS part_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    quantity REAL NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'needed',
                    ordered_at TEXT NOT NULL DEFAULT '',
                    received_at TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_type TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    paid_at TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL,
                    customer_phone TEXT NOT NULL DEFAULT '',
                    relation_type TEXT NOT NULL DEFAULT '',
                    sale_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    due_date TEXT NOT NULL DEFAULT '',
                    total_amount INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sale_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                    item_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    unit_price INTEGER NOT NULL,
                    line_total INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inventory_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    movement_type TEXT NOT NULL,
                    quantity_change REAL NOT NULL,
                    sale_id INTEGER,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inventory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    unit TEXT NOT NULL DEFAULT 'عدد',
                    is_fixed INTEGER NOT NULL DEFAULT 0,
                    stock_quantity REAL NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            for name, category, unit in DEFAULT_INVENTORY_ITEMS:
                now = utc_now()
                connection.execute(
                    """
                    INSERT INTO inventory_items(
                        name, category, unit, is_fixed, created_at, updated_at
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(name) DO NOTHING
                    """,
                    (name, category, unit, now, now),
                )

    @staticmethod
    def _bump(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE meta SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) "
            "WHERE key = 'revision'"
        )

    @staticmethod
    def _revision(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM meta WHERE key = 'revision'"
        ).fetchone()
        return int(row["value"])

    def _get_order_row(self, connection: sqlite3.Connection, order_id: int) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ValueError("دستگاه موردنظر پیدا نشد.")
        return row

    def _order_view(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["order_no"] = result["id"]
        for field in ("power_cable", "data_cable", "customer_called"):
            result[field] = bool(result[field])
        payments = [
            dict(payment)
            for payment in connection.execute(
                "SELECT * FROM payments WHERE owner_type = 'order' AND owner_id = ? "
                "ORDER BY id",
                (result["id"],),
            )
        ]
        paid_amount = sum(payment["amount"] for payment in payments)
        result.update(payment_summary(result["total_cost"], paid_amount))
        result["part_requests"] = [
            dict(part)
            for part in connection.execute(
                "SELECT * FROM part_requests WHERE order_id = ? ORDER BY id",
                (result["id"],),
            )
        ]
        result["media"] = [
            self._media_view(media)
            for media in connection.execute(
                "SELECT * FROM media WHERE order_id = ? ORDER BY id", (result["id"],)
            )
        ]
        result["payments"] = payments
        return result

    def get_order(self, order_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            return self._order_view(connection, self._get_order_row(connection, order_id))

    @staticmethod
    def _media_view(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["url"] = f"/api/media/{result['id']}"
        return result

    def add_media(self, order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        original_name = str(payload.get("original_name", "")).strip()
        stored_name = str(payload.get("stored_name", "")).strip()
        if not original_name or not stored_name:
            raise ValueError("اطلاعات فایل رسانه کامل نیست.")
        with self._lock, self._connect() as connection:
            self._get_order_row(connection, order_id)
            cursor = connection.execute(
                """
                INSERT INTO media(
                    order_id, original_name, stored_name, mime_type, size, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    original_name,
                    stored_name,
                    str(payload.get("mime_type", "application/octet-stream")),
                    int(payload.get("size", 0)),
                    utc_now(),
                ),
            )
            self._bump(connection)
            row = connection.execute(
                "SELECT * FROM media WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return self._media_view(row)

    def get_media(self, media_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM media WHERE id = ?", (media_id,)
            ).fetchone()
            if row is None:
                raise ValueError("رسانه موردنظر پیدا نشد.")
            return self._media_view(row)

    def _get_item_row(self, connection: sqlite3.Connection, item_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            raise ValueError("جنس موردنظر پیدا نشد.")
        return row

    @staticmethod
    def _item_view(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "is_fixed": bool(row["is_fixed"])}

    def _get_sale_row(self, connection: sqlite3.Connection, sale_id: int) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if row is None:
            raise ValueError("فروش موردنظر پیدا نشد.")
        return row

    def _sale_view(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["sale_no"] = result["id"]
        result["items"] = [
            dict(item)
            for item in connection.execute(
                "SELECT * FROM sale_items WHERE sale_id = ? ORDER BY id", (result["id"],)
            )
        ]
        result["payments"] = [
            dict(payment)
            for payment in connection.execute(
                "SELECT * FROM payments WHERE owner_type = 'sale' AND owner_id = ? ORDER BY id",
                (result["id"],),
            )
        ]
        paid_amount = sum(payment["amount"] for payment in result["payments"])
        result.update(payment_summary(result["total_amount"], paid_amount))
        return result

    def get_sale(self, sale_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            return self._sale_view(connection, self._get_sale_row(connection, sale_id))

    def _validated_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        for field, message in (
            ("customer_name", "نام مشتری را وارد کنید."),
            ("device_model", "مدل دستگاه را وارد کنید."),
            ("issue_description", "شرح ایراد را وارد کنید."),
        ):
            result[field] = str(result.get(field, "")).strip()
            if not result[field]:
                raise ValueError(message)
        result["customer_phone"] = normalize_phone(result.get("customer_phone"))
        result["received_at"] = normalize_jalali_date(result.get("received_at"))
        result["promised_at"] = normalize_jalali_date(
            result.get("promised_at", ""), allow_empty=True
        )
        result["status"] = result.get("status") or "received"
        if result["status"] not in ORDER_STATUSES:
            raise ValueError("وضعیت دستگاه معتبر نیست.")
        result["external_center"] = str(result.get("external_center", "")).strip()
        if result["status"] == "sent_external" and not result["external_center"]:
            raise ValueError("نام مرکز تعمیرات مقصد را وارد کنید.")
        for field in (
            "cartridge_type",
            "other_accessories",
            "external_note",
            "service_description",
            "consumed_parts",
            "notes",
        ):
            result[field] = str(result.get(field, "")).strip()
        for field in ("power_cable", "data_cable", "customer_called"):
            result[field] = int(bool(result.get(field, False)))
        result["total_cost"] = parse_amount(result.get("total_cost", 0) or 0)
        return result

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._validated_order(payload)
        now = utc_now()
        fields = (
            "customer_name", "customer_phone", "received_at", "promised_at",
            "device_model", "cartridge_type", "power_cable", "data_cable",
            "other_accessories", "issue_description", "status", "external_center",
            "external_note", "customer_called", "service_description",
            "consumed_parts", "total_cost", "notes",
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO orders({', '.join(fields)}, created_at, updated_at) "
                f"VALUES ({', '.join('?' for _ in fields)}, ?, ?)",
                tuple(data.get(field, "") for field in fields) + (now, now),
            )
            self._bump(connection)
            order_id = cursor.lastrowid
            return self._order_view(connection, self._get_order_row(connection, order_id))

    def update_order(self, order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "customer_name", "customer_phone", "received_at", "promised_at",
            "device_model", "cartridge_type", "power_cable", "data_cable",
            "other_accessories", "issue_description", "status", "external_center",
            "external_note", "service_description", "consumed_parts", "total_cost", "notes",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError("فیلد ویرایش معتبر نیست.")
        with self._lock, self._connect() as connection:
            current = dict(self._get_order_row(connection, order_id))
            merged = {**current, **payload}
            data = self._validated_order(merged)
            paid_row = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) AS paid FROM payments "
                "WHERE owner_type = 'order' AND owner_id = ?",
                (order_id,),
            ).fetchone()
            if data["total_cost"] < paid_row["paid"]:
                raise ValueError("هزینه کل نمی‌تواند کمتر از مبلغ دریافت‌شده باشد.")
            fields = sorted(allowed)
            connection.execute(
                f"UPDATE orders SET {', '.join(f'{field} = ?' for field in fields)}, "
                "updated_at = ? WHERE id = ?",
                tuple(data.get(field, "") for field in fields)
                + (utc_now(), order_id),
            )
            self._bump(connection)
            return self._order_view(connection, self._get_order_row(connection, order_id))

    def set_order_called(self, order_id: int, called: bool) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            self._get_order_row(connection, order_id)
            connection.execute(
                "UPDATE orders SET customer_called = ?, called_at = ?, updated_at = ? WHERE id = ?",
                (int(called), utc_now() if called else "", utc_now(), order_id),
            )
            self._bump(connection)
            return self._order_view(connection, self._get_order_row(connection, order_id))

    def add_inventory_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("نام جنس را وارد کنید.")
        unit = str(payload.get("unit", "عدد")).strip() or "عدد"
        category = str(payload.get("category", "other")).strip() or "other"
        now = utc_now()
        with self._lock, self._connect() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO inventory_items(
                        name, category, unit, is_fixed, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, 0, ?, ?, ?)
                    """,
                    (name, category, unit, str(payload.get("notes", "")).strip(), now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("نام جنس تکراری است.") from exc
            self._bump(connection)
            return self._item_view(self._get_item_row(connection, cursor.lastrowid))

    def restock_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        quantity = parse_quantity(payload.get("quantity", 0))
        now = utc_now()
        with self._lock, self._connect() as connection:
            self._get_item_row(connection, item_id)
            connection.execute(
                "UPDATE inventory_items SET stock_quantity = stock_quantity + ?, "
                "updated_at = ? WHERE id = ?",
                (quantity, now, item_id),
            )
            connection.execute(
                """
                INSERT INTO inventory_movements(
                    item_id, movement_type, quantity_change, note, created_at
                ) VALUES (?, 'restock', ?, ?, ?)
                """,
                (item_id, quantity, str(payload.get("note", "")).strip(), now),
            )
            self._bump(connection)
            return self._item_view(self._get_item_row(connection, item_id))

    def create_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
        sale_type = payload.get("sale_type", "cash")
        if sale_type not in SALE_TYPES:
            raise ValueError("نوع فروش معتبر نیست.")
        customer_name = str(payload.get("customer_name", "")).strip()
        if sale_type == "cash":
            customer_name = customer_name or "مشتری نقدی"
        elif not customer_name:
            raise ValueError("نام مشتری را وارد کنید.")
        raw_phone = str(payload.get("customer_phone", "")).strip()
        if sale_type != "cash" and not raw_phone:
            raise ValueError("شماره تماس مشتری را وارد کنید.")
        customer_phone = normalize_phone(raw_phone) if raw_phone else ""
        relation_type = str(payload.get("relation_type", "")).strip()
        if sale_type != "cash" and not relation_type:
            raise ValueError("نوع رابطه با مشتری را وارد کنید.")
        created_at = normalize_jalali_date(payload.get("created_at") or today_jalali())
        due_date = normalize_jalali_date(payload.get("due_date", ""), allow_empty=True)
        raw_items = payload.get("items") or []
        if not raw_items:
            raise ValueError("حداقل یک کالا به فروش اضافه کنید.")
        initial_payment = parse_amount(payload.get("initial_payment", 0) or 0)

        with self._lock, self._connect() as connection:
            lines = []
            required_by_item: dict[int, float] = {}
            item_rows: dict[int, sqlite3.Row] = {}
            for raw_line in raw_items:
                try:
                    item_id = int(raw_line.get("item_id", 0))
                except (TypeError, ValueError) as exc:
                    raise ValueError("جنس موردنظر پیدا نشد.") from exc
                item = self._get_item_row(connection, item_id)
                quantity = parse_quantity(raw_line.get("quantity", 0))
                unit_price = parse_amount(raw_line.get("unit_price", 0))
                line_total = int(round(quantity * unit_price))
                lines.append((item, quantity, unit_price, line_total))
                required_by_item[item_id] = required_by_item.get(item_id, 0) + quantity
                item_rows[item_id] = item
            for item_id, required in required_by_item.items():
                if required > item_rows[item_id]["stock_quantity"] + 1e-9:
                    raise ValueError(
                        f"موجودی «{item_rows[item_id]['name']}» برای این فروش کافی نیست."
                    )
            total_amount = sum(line[3] for line in lines)
            if total_amount <= 0:
                raise ValueError("مبلغ فروش باید بیشتر از صفر باشد.")
            if sale_type == "cash":
                initial_payment = total_amount
            if initial_payment > total_amount:
                raise ValueError("مبلغ دریافت نمی‌تواند بیشتر از مبلغ فروش باشد.")
            now = utc_now()
            cursor = connection.execute(
                """
                INSERT INTO sales(
                    customer_name, customer_phone, relation_type, sale_type,
                    created_at, due_date, total_amount, note, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_name,
                    customer_phone,
                    relation_type,
                    sale_type,
                    created_at,
                    due_date,
                    total_amount,
                    str(payload.get("note", "")).strip(),
                    now,
                ),
            )
            sale_id = cursor.lastrowid
            for item, quantity, unit_price, line_total in lines:
                connection.execute(
                    """
                    INSERT INTO sale_items(
                        sale_id, item_id, item_name, quantity, unit_price, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (sale_id, item["id"], item["name"], quantity, unit_price, line_total),
                )
                connection.execute(
                    "UPDATE inventory_items SET stock_quantity = stock_quantity - ?, "
                    "updated_at = ? WHERE id = ?",
                    (quantity, now, item["id"]),
                )
                connection.execute(
                    """
                    INSERT INTO inventory_movements(
                        item_id, movement_type, quantity_change, sale_id, note, created_at
                    ) VALUES (?, 'sale', ?, ?, ?, ?)
                    """,
                    (item["id"], -quantity, sale_id, f"فروش شماره {sale_id}", now),
                )
            if initial_payment:
                connection.execute(
                    """
                    INSERT INTO payments(
                        owner_type, owner_id, amount, paid_at, note, created_at
                    ) VALUES ('sale', ?, ?, ?, ?, ?)
                    """,
                    (
                        sale_id,
                        initial_payment,
                        created_at,
                        "دریافت هنگام فروش",
                        now,
                    ),
                )
            self._bump(connection)
            return self._sale_view(connection, self._get_sale_row(connection, sale_id))

    def add_part_request(self, order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("نام قطعه را وارد کنید.")
        quantity = parse_quantity(payload.get("quantity", 1))
        status = payload.get("status", "needed")
        if status not in PART_STATUSES:
            raise ValueError("وضعیت قطعه معتبر نیست.")
        now = utc_now()
        with self._lock, self._connect() as connection:
            self._get_order_row(connection, order_id)
            cursor = connection.execute(
                """
                INSERT INTO part_requests(
                    order_id, name, quantity, status, ordered_at, received_at,
                    note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    name,
                    quantity,
                    status,
                    now if status == "ordered" else "",
                    now if status == "received" else "",
                    str(payload.get("note", "")).strip(),
                    now,
                    now,
                ),
            )
            self._bump(connection)
            row = connection.execute(
                "SELECT * FROM part_requests WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)

    def update_part_request(self, part_id: int, status: str) -> dict[str, Any]:
        if status not in PART_STATUSES:
            raise ValueError("وضعیت قطعه معتبر نیست.")
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM part_requests WHERE id = ?", (part_id,)
            ).fetchone()
            if row is None:
                raise ValueError("قطعه موردنظر پیدا نشد.")
            now = utc_now()
            ordered_at = row["ordered_at"]
            received_at = row["received_at"]
            if status == "ordered" and not ordered_at:
                ordered_at = now
            if status == "received" and not received_at:
                received_at = now
            connection.execute(
                """
                UPDATE part_requests
                SET status = ?, ordered_at = ?, received_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, ordered_at, received_at, now, part_id),
            )
            self._bump(connection)
            updated = connection.execute(
                "SELECT * FROM part_requests WHERE id = ?", (part_id,)
            ).fetchone()
            return dict(updated)

    def add_payment(self, owner_type: str, owner_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if owner_type not in {"order", "sale"}:
            raise ValueError("نوع دریافت معتبر نیست.")
        amount = parse_amount(payload.get("amount", 0))
        if amount == 0:
            raise ValueError("مبلغ دریافت باید بیشتر از صفر باشد.")
        paid_at = normalize_jalali_date(payload.get("paid_at") or today_jalali())
        with self._lock, self._connect() as connection:
            if owner_type == "order":
                owner = self._order_view(connection, self._get_order_row(connection, owner_id))
                total = owner["total_cost"]
            else:
                owner = self._sale_view(connection, self._get_sale_row(connection, owner_id))
                total = owner["total_amount"]
            if owner["paid_amount"] + amount > total:
                raise ValueError("مبلغ دریافت نمی‌تواند بیشتر از مانده باشد.")
            connection.execute(
                """
                INSERT INTO payments(owner_type, owner_id, amount, paid_at, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    owner_type,
                    owner_id,
                    amount,
                    paid_at,
                    str(payload.get("note", "")).strip(),
                    utc_now(),
                ),
            )
            self._bump(connection)
            if owner_type == "order":
                return self._order_view(connection, self._get_order_row(connection, owner_id))
            return self._sale_view(connection, self._get_sale_row(connection, owner_id))

    def get_state(self) -> dict[str, Any]:
        with self._connect() as connection:
            orders = [
                self._order_view(connection, row)
                for row in connection.execute("SELECT * FROM orders ORDER BY id DESC")
            ]
            inventory = [
                {
                    **dict(row),
                    "is_fixed": bool(row["is_fixed"]),
                    "stock_quantity": row["stock_quantity"],
                }
                for row in connection.execute("SELECT * FROM inventory_items ORDER BY id")
            ]
            return {
                "revision": self._revision(connection),
                "orders": orders,
                "inventory_items": inventory,
                "part_requests": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM part_requests ORDER BY id DESC"
                    )
                ],
                "sales": [
                    self._sale_view(connection, row)
                    for row in connection.execute("SELECT * FROM sales ORDER BY id DESC")
                ],
                "payments": [
                    dict(row) for row in connection.execute("SELECT * FROM payments ORDER BY id")
                ],
                "inventory_movements": [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM inventory_movements ORDER BY id"
                    )
                ],
            }
