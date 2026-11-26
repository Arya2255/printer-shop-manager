from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from .repository import Repository


MAX_MEDIA_BYTES = 500 * 1024 * 1024


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    root = Path(data_dir or os.environ.get("PRINTER_SHOP_DATA_DIR", "data")).resolve()
    media_dir = root / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    repository = Repository(root / "shop.db")
    app = FastAPI(title="Printer Shop Sync API", version="1.0.0")
    app.state.repository = repository
    app.state.media_dir = media_dir

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, error: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return repository.get_state()

    @app.post("/api/orders")
    def create_order(payload: dict[str, Any]) -> dict[str, Any]:
        return repository.create_order(payload)

    @app.get("/api/orders/{order_id}")
    def get_order(order_id: int) -> dict[str, Any]:
        return repository.get_order(order_id)

    @app.put("/api/orders/{order_id}")
    def update_order(order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.update_order(order_id, payload)

    @app.post("/api/orders/{order_id}/call")
    def set_called(order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.set_order_called(order_id, bool(payload.get("called")))

    @app.post("/api/orders/{order_id}/parts")
    def add_part(order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.add_part_request(order_id, payload)

    @app.patch("/api/parts/{part_id}")
    def update_part(part_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.update_part_request(part_id, payload.get("status", ""))

    @app.post("/api/orders/{order_id}/payments")
    def add_order_payment(order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.add_payment("order", order_id, payload)

    @app.post("/api/inventory")
    def add_inventory_item(payload: dict[str, Any]) -> dict[str, Any]:
        return repository.add_inventory_item(payload)

    @app.post("/api/inventory/{item_id}/restock")
    def restock(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.restock_item(item_id, payload)

    @app.post("/api/sales")
    def create_sale(payload: dict[str, Any]) -> dict[str, Any]:
        return repository.create_sale(payload)

    @app.get("/api/sales/{sale_id}")
    def get_sale(sale_id: int) -> dict[str, Any]:
        return repository.get_sale(sale_id)

    @app.post("/api/sales/{sale_id}/payments")
    def add_sale_payment(sale_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return repository.add_payment("sale", sale_id, payload)

    @app.post("/api/orders/{order_id}/media")
    async def upload_media(
        order_id: int,
        request: Request,
        filename: str = Query(min_length=1, max_length=255),
    ) -> dict[str, Any]:
        repository.get_order(order_id)
        suffix = Path(filename).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ""
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        temporary_path = media_dir / f"{stored_name}.part"
        final_path = media_dir / stored_name
        size = 0
        try:
            with temporary_path.open("wb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_MEDIA_BYTES:
                        raise ValueError("حجم فایل بیشتر از حد مجاز است.")
                    output.write(chunk)
            temporary_path.replace(final_path)
            return repository.add_media(
                order_id,
                {
                    "original_name": Path(filename).name,
                    "stored_name": stored_name,
                    "mime_type": request.headers.get(
                        "content-type", "application/octet-stream"
                    ).split(";", 1)[0],
                    "size": size,
                },
            )
        except Exception:
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise

    @app.get("/api/media/{media_id}")
    def download_media(media_id: int) -> FileResponse:
        media = repository.get_media(media_id)
        path = media_dir / media["stored_name"]
        if not path.is_file():
            raise ValueError("فایل رسانه روی سرور پیدا نشد.")
        return FileResponse(
            path,
            media_type=media["mime_type"],
            headers={"Cache-Control": "private, max-age=3600"},
        )

    return app


def run() -> None:
    uvicorn.run(
        "shop.server:create_app",
        factory=True,
        host=os.environ.get("PRINTER_SHOP_HOST", "0.0.0.0"),
        port=int(os.environ.get("PRINTER_SHOP_PORT", "8000")),
    )


if __name__ == "__main__":
    run()
