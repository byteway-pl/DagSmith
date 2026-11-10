"""Personal template CRUD; templates are text, never executed on save."""

import ast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import orm, select

from dagsmith.api.deps import db_session
from dagsmith.api.errors import BadRequestError
from dagsmith.api.security import ApiUser, require_edit
from dagsmith.core.db import DagTemplate
from dagsmith.core.templates import owned_template, render_custom

router = APIRouter(tags=["templates"])


class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=200000)


def validate(body):
    if not body.name.strip():
        raise BadRequestError("Template name is required")
    if "{{dag_id}}" not in body.source:
        raise BadRequestError("Include {{dag_id}} so each DAG gets its own ID")
    try:
        ast.parse(render_custom(body.source, "example_dag", ["dagsmith"]))
    except SyntaxError as exc:
        raise BadRequestError(f"Invalid Python template: {exc}") from exc


def detail(template):
    return {"id": template.id, "name": template.name, "source": template.source}


@router.get("/templates")
def list_templates(
    user: ApiUser = Depends(require_edit), session: orm.Session = Depends(db_session)
):
    return (
        [
            detail(t)
            for t in session.scalars(
                select(DagTemplate)
                .where(DagTemplate.owner == user.username)
                .order_by(DagTemplate.name)
            )
        ]
        if user.username
        else []
    )


@router.post("/templates", status_code=201)
def create_template(
    body: TemplateInput,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
):
    if not user.username:
        raise BadRequestError("A named user is required to save personal templates")
    validate(body)
    template = DagTemplate(owner=user.username, name=body.name.strip(), source=body.source)
    session.add(template)
    session.flush()
    return detail(template)


@router.put("/templates/{template_id}")
def update_template(
    template_id: str,
    body: TemplateInput,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
):
    template = owned_template(session, template_id, user.username)
    validate(body)
    template.name, template.source = body.name.strip(), body.source
    session.flush()
    return detail(template)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    user: ApiUser = Depends(require_edit),
    session: orm.Session = Depends(db_session),
):
    session.delete(owned_template(session, template_id, user.username))
