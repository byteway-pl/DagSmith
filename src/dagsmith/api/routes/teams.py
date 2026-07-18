"""Team management (DagSmith admins) + read access for all users."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import orm

from dagsmith.api.deps import db_session
from dagsmith.api.schemas import FileTeamAssign, FileTeamResult, TeamCreate, TeamInfo
from dagsmith.api.security import ApiUser, require_admin, require_read
from dagsmith.core import audit
from dagsmith.core import teams as teams_core
from dagsmith.core.db import Team

router = APIRouter(tags=["teams"])


def _info(team: Team) -> TeamInfo:
    return TeamInfo(
        id=team.id,
        name=team.name,
        description=team.description,
        bundle=team.bundle,
        path_prefix=team.path_prefix,
        git_remote_url=team.git_remote_url,
        git_branch=team.git_branch,
        git_push=team.git_push,
        members=sorted(member.username for member in team.members),
    )


@router.get("/teams")
def list_teams(
    _user: ApiUser = Depends(require_read),
    session: orm.Session = Depends(db_session),
) -> list[TeamInfo]:
    return [_info(team) for team in teams_core.list_teams(session)]


@router.post("/teams", status_code=201)
def create_team(
    body: TeamCreate,
    user: ApiUser = Depends(require_admin),
    session: orm.Session = Depends(db_session),
) -> TeamInfo:
    team = teams_core.create_team(
        session,
        name=body.name,
        bundle=body.bundle,
        path_prefix=body.path_prefix,
        description=body.description,
        git_remote_url=body.git_remote_url,
        git_branch=body.git_branch,
        git_push=body.git_push,
        user=user.username,
    )
    audit.log_event("team_create", user.username, team=body.name)
    return _info(team)


@router.put("/teams/{team_id}")
def update_team(
    team_id: str,
    body: TeamCreate,
    user: ApiUser = Depends(require_admin),
    session: orm.Session = Depends(db_session),
) -> TeamInfo:
    team = teams_core.get_team(session, team_id)
    teams_core.update_team(
        session,
        team,
        name=body.name,
        bundle=body.bundle,
        path_prefix=body.path_prefix,
        description=body.description,
        git_remote_url=body.git_remote_url,
        git_branch=body.git_branch,
        git_push=body.git_push,
    )
    audit.log_event("team_update", user.username, team=body.name)
    return _info(team)


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(
    team_id: str,
    user: ApiUser = Depends(require_admin),
    session: orm.Session = Depends(db_session),
) -> None:
    team = teams_core.get_team(session, team_id)
    audit.log_event("team_delete", user.username, team=team.name)
    session.delete(team)


@router.put("/file-team")
def set_file_team(
    body: FileTeamAssign,
    user: ApiUser = Depends(require_admin),
    session: orm.Session = Depends(db_session),
) -> FileTeamResult:
    """Admin: assign a DAG file to a team (override) or clear the override."""
    team = teams_core.set_file_team(
        session, body.bundle, body.rel_path, body.team_id, user.username
    )
    audit.log_event(
        "file_team_set",
        user.username,
        bundle=body.bundle,
        rel_path=body.rel_path,
        team=team.name if team else None,
    )
    return FileTeamResult(
        bundle=body.bundle, rel_path=body.rel_path, team=team.name if team else None
    )


@router.post("/teams/{team_id}/members/{username}", status_code=204)
def add_member(
    team_id: str,
    username: str,
    user: ApiUser = Depends(require_admin),
    session: orm.Session = Depends(db_session),
) -> None:
    team = teams_core.get_team(session, team_id)
    teams_core.add_member(session, team, username)
    audit.log_event("team_member_add", user.username, team=team.name, member=username)


@router.delete("/teams/{team_id}/members/{username}", status_code=204)
def remove_member(
    team_id: str,
    username: str,
    user: ApiUser = Depends(require_admin),
    session: orm.Session = Depends(db_session),
) -> None:
    team = teams_core.get_team(session, team_id)
    teams_core.remove_member(session, team, username)
    audit.log_event("team_member_remove", user.username, team=team.name, member=username)
