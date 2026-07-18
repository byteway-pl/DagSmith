from __future__ import annotations

import pytest

from dagsmith import config


def test_defaults_without_airflow() -> None:
    assert config.get_bool("deploy_enabled") is False
    assert config.get_int("autosave_interval") == 30
    assert config.get_list("allowed_bundles") == ["*"]
    assert config.get_list("editors") == []


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRFLOW__DAGSMITH__DEPLOY_ENABLED", "true")
    monkeypatch.setenv("AIRFLOW__DAGSMITH__EDITORS", "alice, bob")
    assert config.get_bool("deploy_enabled") is True
    assert config.get_list("editors") == ["alice", "bob"]


def test_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        config.get_str("nonexistent_key")
