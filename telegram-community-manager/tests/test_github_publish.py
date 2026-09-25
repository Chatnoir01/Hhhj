from app import github_publish


def test_public_codespace_url(monkeypatch):
    monkeypatch.setenv("CODESPACE_NAME", "improved-telegram-abc")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")

    assert (
        github_publish.public_codespace_url(8000)
        == "https://improved-telegram-abc-8000.app.github.dev"
    )


def test_publish_codespace_port_uses_github_cli(monkeypatch):
    monkeypatch.setenv("CODESPACE_NAME", "improved-telegram-abc")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    monkeypatch.setattr(github_publish.shutil, "which", lambda _: "/usr/bin/gh")

    seen = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            seen["timeout"] = timeout
            return "", ""

        def kill(self):
            raise AssertionError("kill should not be called")

    def fake_popen(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(github_publish.subprocess, "Popen", fake_popen)

    result = github_publish.publish_codespace_port(8000)

    assert result["ok"] is True
    assert result["visibility"] == "public"
    assert result["url"] == "https://improved-telegram-abc-8000.app.github.dev"
    assert seen["args"] == [
        "gh",
        "codespace",
        "ports",
        "visibility",
        "8000:public",
        "-c",
        "improved-telegram-abc",
    ]
    assert seen["timeout"] == 30
