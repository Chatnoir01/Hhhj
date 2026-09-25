from app.importers import normalize_username


def test_normalizes_at_username():
    assert normalize_username("@Timal_123") == "timal_123"


def test_normalizes_tme_url():
    assert normalize_username("https://t.me/Timal_123") == "timal_123"


def test_rejects_invalid_username():
    assert normalize_username("@@bad name") is None
