"""Plugin configuration: ``[dagsmith]`` section of airflow.cfg / ``AIRFLOW__DAGSMITH__*`` env.

Airflow is imported lazily so that unit tests and the ``python -m dagsmith`` CLI
work in environments without a configured Airflow.
"""

from __future__ import annotations

import os

_SECTION = "dagsmith"

_DEFAULTS: dict[str, str] = {
    "deploy_enabled": "False",
    "allowed_bundles": "*",
    "editors": "",
    "deployers": "",
    "admins": "",
    "autosave_interval": "30",
    "auto_versions_keep": "20",
    "backup_retention": "50",
    "validation_timeout": "20",
    "auto_migrate": "True",
    "catalog_ttl": "600",
    "git_commit": "False",
    "git_push": "False",
    "dev_bundle_url": "",
}

_TRUTHY = frozenset({"true", "1", "t", "yes", "y", "on"})


def _raw(key: str) -> str:
    if key not in _DEFAULTS:
        raise KeyError(f"Unknown [{_SECTION}] config key: {key}")
    env_value = os.environ.get(f"AIRFLOW__{_SECTION.upper()}__{key.upper()}")
    if env_value is not None:
        return env_value
    try:
        from airflow.configuration import conf

        value = conf.get(_SECTION, key, fallback=None)
        if value is not None:
            return value
    except Exception:
        pass
    return _DEFAULTS[key]


def get_str(key: str) -> str:
    return _raw(key)


def get_bool(key: str) -> bool:
    return _raw(key).strip().lower() in _TRUTHY


def get_int(key: str) -> int:
    return int(_raw(key).strip())


def get_list(key: str) -> list[str]:
    return [item.strip() for item in _raw(key).split(",") if item.strip()]


def sql_alchemy_url() -> str:
    """Database URL: DagSmith override, else Airflow's metadata DB connection."""
    override = os.environ.get("DAGSMITH_SQL_ALCHEMY_CONN")
    if override:
        return override
    from airflow.configuration import conf

    return conf.get("database", "sql_alchemy_conn")
