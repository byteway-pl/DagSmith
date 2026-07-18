"""Authentication and authorization for the DagSmith API.

Uses Airflow's Auth Manager: the JWT comes either as a Bearer header or from the
UI session cookie (``_token``), which the embedded react_app sends automatically
on same-origin requests. Airflow imports are function-local so this module can
be imported (and dependency-overridden) in unit tests without Airflow installed.

Permission model (see ARCHITECTURE.md §4.4):
- read  -> authenticated + DAG read permission
- edit  -> DAG edit permission, optionally restricted to ``[dagsmith] editors``
- deploy-> edit + ``deploy_enabled`` + optionally restricted to ``[dagsmith] deployers``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request

from dagsmith.api.errors import ForbiddenError, UnauthorizedError
from dagsmith.config import get_bool, get_list


@dataclass
class ApiUser:
    username: str | None
    airflow_user: Any


COOKIE_NAME_JWT_TOKEN = "_token"  # airflow.api_fastapi.core_api.security.COOKIE_NAME_JWT_TOKEN


async def get_current_user(request: Request) -> ApiUser:
    header = request.headers.get("Authorization")
    if header and header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1]
    else:
        token = request.cookies.get(COOKIE_NAME_JWT_TOKEN)
    if not token:
        raise UnauthorizedError("Not authenticated")

    from airflow.api_fastapi.core_api.security import resolve_user_from_token

    user = await resolve_user_from_token(token)
    name = user.get_name() if hasattr(user, "get_name") else None
    return ApiUser(username=name, airflow_user=user)


def _is_authorized_dag(user: ApiUser, method: str) -> bool:
    from airflow.api_fastapi.app import get_auth_manager

    return bool(get_auth_manager().is_authorized_dag(method=method, user=user.airflow_user))


def _in_group(user: ApiUser, config_key: str) -> bool:
    """True when the config list is empty (no restriction) or contains the user."""
    allowed = get_list(config_key)
    return not allowed or (user.username is not None and user.username in allowed)


async def require_read(user: ApiUser = Depends(get_current_user)) -> ApiUser:
    if not _is_authorized_dag(user, "GET"):
        raise ForbiddenError("DAG read permission required")
    return user


async def require_edit(user: ApiUser = Depends(get_current_user)) -> ApiUser:
    if not _is_authorized_dag(user, "PUT"):
        raise ForbiddenError("DAG edit permission required")
    if not _in_group(user, "editors"):
        raise ForbiddenError("User is not on the [dagsmith] editors list")
    return user


async def require_deploy(user: ApiUser = Depends(require_edit)) -> ApiUser:
    if not get_bool("deploy_enabled"):
        raise ForbiddenError("Deploy is disabled ([dagsmith] deploy_enabled = False)")
    if not _in_group(user, "deployers"):
        raise ForbiddenError("User is not on the [dagsmith] deployers list")
    return user


def is_admin(user: ApiUser) -> bool:
    """DagSmith admin: on the [dagsmith] admins list; with no list configured,
    anyone with deploy rights counts as admin."""
    admins = get_list("admins")
    if admins:
        return user.username is not None and user.username in admins
    try:
        return (
            get_bool("deploy_enabled")
            and _is_authorized_dag(user, "PUT")
            and _in_group(user, "editors")
            and _in_group(user, "deployers")
        )
    except Exception:
        return False


async def require_admin(user: ApiUser = Depends(get_current_user)) -> ApiUser:
    if not is_admin(user):
        raise ForbiddenError("DagSmith admin rights required ([dagsmith] admins)")
    return user


def user_capabilities(user: ApiUser) -> tuple[bool, bool, bool]:
    """(can_edit, can_deploy, is_admin) for the config endpoint — never raises."""
    try:
        can_edit = _is_authorized_dag(user, "PUT") and _in_group(user, "editors")
    except Exception:
        can_edit = False
    can_deploy = can_edit and get_bool("deploy_enabled") and _in_group(user, "deployers")
    return can_edit, can_deploy, is_admin(user)
