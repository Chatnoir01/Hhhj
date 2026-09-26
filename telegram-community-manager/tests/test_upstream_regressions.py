from pathlib import Path

UPSTREAM_FORBIDDEN_PATTERNS = (
    "taskkill",
    "python.exe",
    'cors_allowed_origins="*"',
)

def test_active_app_does_not_contain_upstream_destructive_patterns():
    app_dir = Path(__file__).parents[1] / "app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in app_dir.rglob("*.py"))
    for pattern in UPSTREAM_FORBIDDEN_PATTERNS:
        assert pattern not in source
