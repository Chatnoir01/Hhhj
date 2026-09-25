from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_is_available_without_exposing_secret_values():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Telegram Community Manager" in response.text
    assert "Premier setup" in response.text
    assert "Envoyer le code Telegram" in response.text
    assert "TELEGRAM_API_HASH=" not in response.text
    assert "TELEGRAM_BOT_TOKEN=" not in response.text
