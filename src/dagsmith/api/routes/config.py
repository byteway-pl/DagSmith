from __future__ import annotations

from fastapi import APIRouter, Depends

from dagsmith.api.schemas import ConfigInfo
from dagsmith.api.security import ApiUser, get_current_user, user_capabilities
from dagsmith.config import get_bool, get_int

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config(user: ApiUser = Depends(get_current_user)) -> ConfigInfo:
    can_edit, can_deploy, admin = user_capabilities(user)
    return ConfigInfo(
        deploy_enabled=get_bool("deploy_enabled"),
        autosave_interval=get_int("autosave_interval"),
        can_edit=can_edit,
        can_deploy=can_deploy,
        is_admin=admin,
        username=user.username,
    )
