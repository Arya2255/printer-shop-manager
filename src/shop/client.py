from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

import httpx


class ApiError(RuntimeError):
    pass


class HttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise ApiError("ارتباط با سرور برقرار نشد. آدرس سرور و اینترنت را بررسی کنید.") from error
        if response.is_error:
            try:
                message = response.json().get("detail", response.text)
            except (ValueError, AttributeError):
                message = response.text
            if not isinstance(message, str):
                message = "سرور درخواست را نپذیرفت."
            raise ApiError(message or "سرور درخواست را نپذیرفت.")
        return response.json()

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, bool]:
        return self._request("GET", "/api/health")

    def get_state(self) -> dict[str, Any]:
        return self._request("GET", "/api/state")

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/orders", json=payload)

    def get_order(self, order_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/orders/{order_id}")

    def update_order(self, order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/orders/{order_id}", json=payload)

    def set_order_called(self, order_id: int, called: bool) -> dict[str, Any]:
        return self._request("POST", f"/api/orders/{order_id}/call", json={"called": called})

    def add_part_request(self, order_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/orders/{order_id}/parts", json=payload)

    def update_part_request(self, part_id: int, status: str) -> dict[str, Any]:
        return self._request("PATCH", f"/api/parts/{part_id}", json={"status": status})

    def add_payment(self, owner_type: str, owner_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/{'orders' if owner_type == 'order' else 'sales'}/{owner_id}/payments", json=payload
        )

    def add_inventory_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/inventory", json=payload)

    def restock_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/inventory/{item_id}/restock", json=payload)

    def create_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/sales", json=payload)

    def get_sale(self, sale_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/sales/{sale_id}")

    def upload_media(self, order_id: int, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as source:
            return self._request(
                "POST",
                f"/api/orders/{order_id}/media",
                params={"filename": path.name},
                content=source,
                headers={"Content-Type": mime_type},
            )

    def media_url(self, media: dict[str, Any]) -> str:
        return f"{self.base_url}{media['url']}"
