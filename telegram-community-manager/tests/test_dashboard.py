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


def test_dashboard_has_resilient_async_dry_run_and_manual_message_composer():
    client = TestClient(app)
    response = client.get("/")
    text = response.text

    assert response.status_code == 200
    assert "/run-async" in text
    assert "/campaign-runs/" in text
    assert "Message d'invitation" in text
    assert "@chatnoir_uhq" in text
    assert "[LIEN TELEGRAM]" in text
    assert "navigator.clipboard.writeText" in text
    assert "DM massif" in text
    assert "</button>\\n" not in text
