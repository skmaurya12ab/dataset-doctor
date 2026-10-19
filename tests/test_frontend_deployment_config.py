import json
import re
from pathlib import Path


def test_vercel_preserves_api_proxy_and_clean_url_spa_fallback() -> None:
    config_path = Path(__file__).parents[1] / "frontend" / "vercel.json"
    config = json.loads(config_path.read_text())

    assert config["cleanUrls"] is True
    rewrites = config["rewrites"]
    assert rewrites[0]["source"] == "/api/:path*"
    assert rewrites[0]["destination"] == (
        "https://REPLACE_WITH_RENDER_SERVICE.onrender.com/api/:path*"
    )
    assert rewrites[1] == {"source": "/(.*)", "destination": "/"}

    # These client routes must reach the SPA entrypoint after a direct visit or refresh.
    for route in ("/login", "/register", "/verify-email", "/reset-password", "/remediation"):
        assert re.fullmatch(rewrites[-1]["source"], route)
        assert rewrites[-1]["destination"] == "/"

    dockerfile = (config_path.parents[1] / "Dockerfile").read_text()
    assert "ca-certificates \\" in dockerfile
    assert "update-ca-certificates" in dockerfile
    port_expr = "$" + "{PORT:-8000}"
    assert "--port " + port_expr in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "curl \\\n" in dockerfile  # curl is installed in the image already.
    healthcheck = re.search(
        r"(?m)^HEALTHCHECK\b[^\n]*\\\n[ \t]*CMD[ \t]+([^\n]+)$",
        dockerfile,
    )
    assert healthcheck, "Dockerfile HEALTHCHECK must use valid CMD shell-form syntax."
    assert "CMD-SHELL" not in healthcheck.group(1)
    assert "127.0.0.1:" + port_expr + "/health" in healthcheck.group(1)
    assert "--max-time 4" in healthcheck.group(1)


def test_legacy_production_compose_and_env_backup_ignore_rules() -> None:
    root = Path(__file__).parents[1]
    compose = (root / "docker-compose.prod.yml").read_text()
    assert "LEGACY / UNSUPPORTED" in compose
    assert "docs/production-deployment-guide.md" in compose

    gitignore = (root / ".gitignore").read_text()
    assert re.search(r"(?m)^\.env$", gitignore)
    assert re.search(r"(?m)^\.env\.before-\*$", gitignore)
