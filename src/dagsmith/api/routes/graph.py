from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dagsmith.api.errors import BadRequestError
from dagsmith.api.security import require_edit, require_read
from dagsmith.core.codegen import generate_source
from dagsmith.core.model import GraphModel, GraphValidationError
from dagsmith.core.parser import ParseError, parse_graph

router = APIRouter(tags=["graph"])


class CodegenRequest(BaseModel):
    graph: GraphModel
    # When given, apply minimal formatting-preserving edits to this source
    # instead of generating a file from scratch.
    base_source: str | None = None


class CodegenResult(BaseModel):
    source: str


class ParseRequest(BaseModel):
    source: str


class ParseResult(BaseModel):
    graph: GraphModel | None
    warnings: list[str]
    error: str | None = None


@router.post("/codegen", dependencies=[Depends(require_edit)])
def codegen(body: CodegenRequest) -> CodegenResult:
    try:
        return CodegenResult(source=generate_source(body.graph, body.base_source))
    except (GraphValidationError, ParseError) as exc:
        raise BadRequestError(str(exc)) from exc


@router.post("/parse", dependencies=[Depends(require_read)])
def parse(body: ParseRequest) -> ParseResult:
    try:
        graph, warnings = parse_graph(body.source)
        return ParseResult(graph=graph, warnings=warnings)
    except ParseError as exc:
        # Not an HTTP error: an unparseable file simply has no canvas view.
        return ParseResult(graph=None, warnings=[], error=str(exc))
