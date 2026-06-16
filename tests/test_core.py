import json
from pathlib import Path

import pytest

from occamdraft.config import load_config, resolve_profile_secrets
from occamdraft.explore import canonicalize, route_family


def test_canonicalize():
    assert canonicalize("HTTP://Example.com/users/?b=2&utm=x&a=1#top") == "http://example.com/users"
    assert canonicalize("HTTP://Example.com/users/?b=2&utm=x&a=1#top", ["a", "b"]) == (
        "http://example.com/users?a=1&b=2"
    )


def test_route_family():
    assert route_family("https://example.com/users/123") == "/users/{id}"


def test_load_config_expands_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_USER", "admin")
    monkeypatch.setenv("TEST_PASSWORD", "secret")
    data = {
        "version": 1,
        "suts": [{
            "sut_id": "demo", "site_name": "demo", "base_url": "https://example.com",
            "allowed_origins": ["https://example.com"],
            "profiles": [{
                "profile_id": "admin", "role": "admin", "start_routes": ["/"],
                "auth": {
                    "type": "form", "username": "${TEST_USER}", "password": "${TEST_PASSWORD}",
                    "username_selector": "#user", "password_selector": "#password",
                    "submit_selector": "#submit"
                }
            }]
        }]
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    config = load_config(path)
    assert config.suts[0].profiles[0].auth.username.get_secret_value() == "admin"


def test_missing_environment_variable(tmp_path: Path):
    path = tmp_path / "profile.json"
    path.write_text('{"version":1,"suts":"${MISSING_OCCAMDRAFT_VALUE}"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Missing environment variable"):
        load_config(path)


def test_resolve_only_selected_profile_secrets(monkeypatch):
    monkeypatch.setenv("TEST_USER", "admin")
    config = load_config(Path("profiles/profile.example.json"), resolve_env=False)
    profile = config.suts[0].profiles[0]
    with pytest.raises(ValueError, match="TIMEOFF_ADMIN_USERNAME"):
        resolve_profile_secrets(profile)
