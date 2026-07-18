"""Teams: ownership of bundle sub-trees and per-team file access.

A team owns ``(bundle, path_prefix)``. Files under an owned prefix are
editable only by team members (DagSmith admins bypass). Files outside any
team prefix follow the global rules unchanged. When several prefixes match,
the longest one wins.
"""

from __future__ import annotations

from sqlalchemy import orm, select

from dagsmith.api.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from dagsmith.core.db import FileTeam, Team, TeamMember


def list_teams(session: orm.Session) -> list[Team]:
    return list(session.scalars(select(Team).order_by(Team.name)))


def get_team(session: orm.Session, team_id: str) -> Team:
    team = session.get(Team, team_id)
    if team is None:
        raise NotFoundError(f"Team not found: {team_id}")
    return team


def create_team(
    session: orm.Session,
    *,
    name: str,
    bundle: str,
    path_prefix: str,
    description: str | None,
    git_remote_url: str | None,
    git_branch: str,
    git_push: bool,
    user: str | None,
) -> Team:
    if session.scalars(select(Team).where(Team.name == name)).first() is not None:
        raise ConflictError(f"Team {name!r} already exists")
    team = Team(
        name=name,
        bundle=bundle,
        path_prefix=path_prefix.strip("/"),
        description=description,
        git_remote_url=(git_remote_url or "").strip() or None,
        git_branch=git_branch.strip() or "main",
        git_push=git_push,
        created_by=user,
    )
    session.add(team)
    session.flush()
    return team


def update_team(
    session: orm.Session,
    team: Team,
    *,
    name: str,
    bundle: str,
    path_prefix: str,
    description: str | None,
    git_remote_url: str | None,
    git_branch: str,
    git_push: bool,
) -> Team:
    team.name = name
    team.bundle = bundle
    team.path_prefix = path_prefix.strip("/")
    team.description = description
    team.git_remote_url = (git_remote_url or "").strip() or None
    team.git_branch = git_branch.strip() or "main"
    team.git_push = git_push
    return team


def add_member(session: orm.Session, team: Team, username: str) -> None:
    exists = session.scalars(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.username == username
        )
    ).first()
    if exists is None:
        session.add(TeamMember(team_id=team.id, username=username))


def remove_member(session: orm.Session, team: Team, username: str) -> None:
    member = session.scalars(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.username == username
        )
    ).first()
    if member is not None:
        session.delete(member)


def user_teams(session: orm.Session, username: str | None) -> list[Team]:
    if username is None:
        return []
    return list(
        session.scalars(
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.username == username)
            .order_by(Team.name)
        )
    )


def file_override(session: orm.Session, bundle: str, rel_path: str) -> Team | None:
    """Admin-set per-file team assignment, if any."""
    row = session.scalars(
        select(FileTeam).where(FileTeam.bundle == bundle, FileTeam.rel_path == rel_path)
    ).first()
    return row.team if row is not None else None


def file_team_overrides(session: orm.Session, bundle: str) -> dict[str, Team]:
    """All per-file overrides in a bundle, keyed by rel_path (for listings)."""
    return {
        row.rel_path: row.team
        for row in session.scalars(select(FileTeam).where(FileTeam.bundle == bundle))
    }


def prefix_team_for_path(session: orm.Session, bundle: str, rel_path: str) -> Team | None:
    """Owning team by directory: longest matching (bundle, path_prefix)."""
    best: Team | None = None
    for team in session.scalars(select(Team).where(Team.bundle == bundle)):
        prefix = team.path_prefix
        matches = prefix == "" or rel_path == prefix or rel_path.startswith(prefix + "/")
        if matches and (best is None or len(prefix) > len(best.path_prefix)):
            best = team
    return best


def team_for_path(session: orm.Session, bundle: str, rel_path: str) -> Team | None:
    """Owning team of a file: the admin override wins, else the path prefix."""
    override = file_override(session, bundle, rel_path)
    if override is not None:
        return override
    return prefix_team_for_path(session, bundle, rel_path)


def set_file_team(
    session: orm.Session,
    bundle: str,
    rel_path: str,
    team_id: str | None,
    user: str | None,
) -> Team | None:
    """Set (or clear, with ``team_id=None``) the per-file team override."""
    existing = session.scalars(
        select(FileTeam).where(FileTeam.bundle == bundle, FileTeam.rel_path == rel_path)
    ).first()
    if team_id is None:
        if existing is not None:
            session.delete(existing)
        return None
    team = get_team(session, team_id)
    if team.bundle != bundle:
        raise BadRequestError(
            f"Team {team.name!r} belongs to bundle {team.bundle!r}, not {bundle!r}"
        )
    if existing is not None:
        existing.team_id = team.id
        existing.assigned_by = user
    else:
        session.add(
            FileTeam(bundle=bundle, rel_path=rel_path, team_id=team.id, assigned_by=user)
        )
    return team


def is_member(session: orm.Session, team: Team, username: str | None) -> bool:
    if username is None:
        return False
    return any(member.username == username for member in team.members)


def ensure_file_access(
    session: orm.Session,
    bundle: str,
    rel_path: str,
    username: str | None,
    is_admin: bool,
) -> Team | None:
    """Raise 403 when the file is owned by a team the user is not part of."""
    team = team_for_path(session, bundle, rel_path)
    if team is None or is_admin or is_member(session, team, username):
        return team
    raise ForbiddenError(
        f"File {rel_path!r} is managed by team {team.name!r} — ask a DagSmith admin "
        "or a team member for access"
    )
