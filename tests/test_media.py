import pytest

from shop.repository import Repository
from shop.utils import today_jalali


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "shop.db")


@pytest.fixture
def order(repository):
    return repository.create_order(
        {
            "customer_name": "مشتری رسانه",
            "customer_phone": "09121112233",
            "received_at": today_jalali(),
            "device_model": "HP 1102",
            "issue_description": "روشن نمی‌شود",
        }
    )


def test_media_metadata_is_attached_to_order_without_file_contents(repository, order):
    media = repository.add_media(
        order["id"],
        {
            "original_name": "خرابی.jpg",
            "stored_name": "stored-file.jpg",
            "mime_type": "image/jpeg",
            "size": 12345,
        },
    )

    assert media["id"]
    assert media["original_name"] == "خرابی.jpg"
    assert media["url"].endswith(str(media["id"]))
    assert repository.get_order(order["id"])["media"] == [media]
    assert "bytes" not in media


def test_missing_order_or_media_is_rejected(repository, order):
    with pytest.raises(ValueError, match="دستگاه"):
        repository.add_media(999, {"original_name": "x.jpg", "stored_name": "x"})
    media = repository.add_media(
        order["id"], {"original_name": "x.jpg", "stored_name": "x"}
    )
    assert repository.get_media(media["id"])["stored_name"] == "x"
    with pytest.raises(ValueError, match="رسانه"):
        repository.get_media(999)
