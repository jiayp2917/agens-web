"""Static deployment contract coverage for the production Compose stack."""

from __future__ import annotations

from pathlib import Path

import yaml

from agens_novel.llm.url_security import OFFICIAL_MODEL_HOSTS

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = ROOT / "deploy" / "docker-compose.yml"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_runtime_services_are_internal_and_hardened() -> None:
    compose = _compose()
    services = compose["services"]

    for name in ("agens-web-migrate", "agens-web", "redis", "egress-proxy"):
        service = services[name]
        assert "ports" not in service
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["pids_limit"]
        assert service["mem_limit"]
        assert service["cpus"]

    assert services["redis"]["user"] == "redis"
    assert compose["networks"]["agens_runtime"]["internal"] is True
    assert services["redis"]["networks"] == ["agens_runtime"]
    assert services["egress-proxy"]["networks"] == ["agens_runtime", "agens_egress"]
    assert "agens_egress" not in services["agens-web"]["networks"]


def test_application_requires_healthy_redis_and_proxy() -> None:
    dependencies = _compose()["services"]["agens-web"]["depends_on"]

    assert dependencies["redis"]["condition"] == "service_healthy"
    assert dependencies["egress-proxy"]["condition"] == "service_healthy"
    assert dependencies["agens-web-migrate"]["condition"] == "service_completed_successfully"


def test_squid_acl_allows_only_model_https_and_rejects_private_destinations() -> None:
    entrypoint = (ROOT / "deploy" / "squid" / "entrypoint.sh").read_text(encoding="utf-8")

    for hostname in OFFICIAL_MODEL_HOSTS:
        assert hostname in entrypoint
    for blocked_range in (
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    ):
        assert blocked_range in entrypoint

    deny_private = entrypoint.index("http_access deny private_dst")
    allow_models = entrypoint.index("http_access allow model_hosts")
    deny_all = entrypoint.index("http_access deny all", allow_models)
    assert "http_access deny !CONNECT" in entrypoint
    assert "http_access deny !SSL_ports" in entrypoint
    assert deny_private < allow_models < deny_all


def test_host_acl_blocks_application_proxy_bypass() -> None:
    script = (ROOT / "deploy" / "apply-egress-acl.sh").read_text(encoding="utf-8")

    assert "DOCKER-USER" in script
    assert 'AGENS_DB_PORT_FOR_ACL' in script
    assert '-p tcp --dport 3128 -j ACCEPT' in script
    assert '-p tcp --dport 6379 -j ACCEPT' in script
    assert 'iptables -A "$chain" -s "$app_ip" -j REJECT' in script
