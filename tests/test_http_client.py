import json

import httpx
import pytest

from shop.client import ApiError, HttpClient


def test_http_client_uses_central_api_and_returns_json():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/state":
            return httpx.Response(200, json={"revision": 4, "orders": []})
        if request.url.path == "/api/orders/7/call":
            payload = json.loads(request.content)
            return httpx.Response(200, json={"id": 7, "customer_called": payload["called"]})
        return httpx.Response(404, json={"detail": "not found"})

    client = HttpClient("http://server/", transport=httpx.MockTransport(handler))
    assert client.get_state()["revision"] == 4
    assert client.set_order_called(7, True)["customer_called"] is True
    assert str(requests[0].url) == "http://server/api/state"
    assert requests[1].method == "POST"


def test_server_validation_message_is_preserved():
    def handler(_request):
        return httpx.Response(400, json={"detail": "موجودی کافی نیست."})

    client = HttpClient("http://server", transport=httpx.MockTransport(handler))
    with pytest.raises(ApiError, match="موجودی کافی نیست"):
        client.create_sale({"items": []})


def test_network_failure_has_clear_persian_error():
    def handler(_request):
        raise httpx.ConnectError("offline")

    client = HttpClient("http://server", transport=httpx.MockTransport(handler))
    with pytest.raises(ApiError, match="ارتباط با سرور"):
        client.get_state()


def test_media_upload_uses_file_name_content_type_and_bytes(tmp_path):
    media_file = tmp_path / "printer photo.jpg"
    media_file.write_bytes(b"actual-file-bytes")
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["content"] = request.content
        captured["content_type"] = request.headers["content-type"]
        return httpx.Response(
            200,
            json={"id": 3, "url": "/api/media/3", "original_name": media_file.name},
        )

    client = HttpClient("http://server", transport=httpx.MockTransport(handler))
    result = client.upload_media(2, media_file)

    assert result["id"] == 3
    assert captured["content"] == b"actual-file-bytes"
    assert captured["content_type"] == "image/jpeg"
    assert "filename=printer+photo.jpg" in captured["url"]
    assert client.media_url(result) == "http://server/api/media/3"
