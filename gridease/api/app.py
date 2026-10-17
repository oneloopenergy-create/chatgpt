"""GridEasy HTTP API (FastAPI). Run: uvicorn gridease.api.app:app --reload"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, JSONResponse
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..calc.bess import size_bess
from ..calc.engineering import run_all
from ..compliance.checks import run_checks
from ..core.model import Project, RfiItem, SignOff, Source, SourceKind, Stage, now
from ..core.store import ProjectStore, ProjectConflict
from ..core.validation import validate_parameter
from ..delivery.model import Delivery
from ..delivery.readiness import workflow, design_hash
from ..intake.extract import RuleExtractor, apply_extraction
from ..package.bundle import PackageBlocked, blockers, build_package
from ..package.documents import GENERATORS, generate_all
from ..rules.engine import Evaluation, evaluate_fields, evaluate_project, project_fields
from ..rules.library import list_packs

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="GridEasy", version="0.2.0",
              description="AI engineering platform for Australian distribution network connections — drafts only; sign-off and submission by a registered engineer")
_store: ProjectStore | None = None


@app.exception_handler(ProjectConflict)
async def conflict_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def refresh_design(p: Project) -> None:
    """Keep the SLD current whenever design inputs change; retain visible failure reasons."""
    p.calculation_notes = run_all(p)
    from ..delivery.documents import GENERATORS as engineering_generators
    _, errors = generate_all(p, ["sld"] + (list(engineering_generators) if p.delivery is not None else []))
    p.document_errors.pop("sld", None)
    p.document_errors.update(errors)


def store() -> ProjectStore:
    global _store
    if _store is None:
        _store = ProjectStore()
    return _store


def load(pid: str, request: Request, st: ProjectStore = Depends(store)) -> Project:
    try:
        p = st.load(pid)
        expected = request.headers.get("X-Project-Revision")
        if request.method not in ("GET", "HEAD") and expected is not None:
            try:
                revision = int(expected)
            except ValueError:
                raise HTTPException(422, "Invalid project revision")
            if revision != p.revision:
                raise ProjectConflict("Another employee changed this project. Reload it before saving your changes.")
        return p
    except KeyError:
        raise HTTPException(404, "Project not found")


def summary(p: Project) -> dict[str, Any]:
    findings = run_checks(p)
    return {
        "calculation_notes": p.calculation_notes, "document_errors": p.document_errors,
        "revision": p.revision,
        "delivery_hash": design_hash(p) if p.delivery is not None else None,
        "delivery": p.delivery.model_dump(mode="json") if p.delivery is not None else None,
        "workflow": workflow(p) if p.delivery is not None else [],
        "id": p.id, "name": p.name, "stage": p.stage, "created_at": p.created_at,
        "params": {k: v.model_dump(mode="json") | {"is_assumption": v.is_assumption} for k, v in sorted(p.params.items())},
        "assumptions": [a.key for a in p.assumptions()],
        "documents": [{"doc_id": d.doc_id, "title": d.title, "filename": d.filename, "status": d.status,
                       "requires_signoff": d.requires_signoff, "signed": p.is_signed(d.doc_id), "todo": d.todo,
                       "generated_at": d.generated_at} for d in p.documents.values()],
        "stale_documents": p.stale_documents(),
        "findings": [f.model_dump() for f in findings],
        "blockers": blockers(p),
        "signoffs": [s.model_dump() for s in p.signoffs],
        "rfi_rounds": [r.model_dump() for r in p.rfi_rounds],
    }


# ---------------------------------------------------------------- models
class CreateProject(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    brief: str | None = None
    engineering_delivery: bool = True


class IntakeBody(BaseModel):
    text: str
    source_ref: str = "brief"


class ParamBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    value: Any
    unit: str | None = None
    ref: str = Field(default="ui", min_length=1)
    actor: str = Field(default="user", min_length=1)


class ParameterUpdate(ParamBody):
    key: str
    remove: bool = False


class ParameterUpdates(BaseModel):
    updates: list[ParameterUpdate] = Field(min_length=1, max_length=100)


class ConfirmBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    engineer: str = Field(min_length=1)


class RfiBody(BaseModel):
    items: list[RfiItem] = Field(min_length=1)


class RfiRespond(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    item_index: int = Field(ge=0)
    response: str = Field(min_length=1)


# ---------------------------------------------------------------- routes
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get('/delivery.js', include_in_schema=False)
def delivery_javascript():
    return FileResponse(WEB / 'delivery.js', media_type='application/javascript')


@app.get("/api/rules")
def rules() -> list[dict[str, Any]]:
    return list_packs()


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    """All source registries (NSW Data Master, DNSP Evidence Pack), keyed by registry id."""
    out = {}
    for f in sorted((Path(__file__).resolve().parent.parent / "rules" / "sources").glob("*.yaml")):
        reg = yaml.safe_load(f.read_text(encoding="utf-8"))
        out[reg["id"]] = reg
    return out


def _evaluation(ev: Evaluation) -> dict[str, Any]:
    return {"status": ev.status, "pack": ev.pack, "rule_ids": ev.rule_ids, "flags": ev.flags,
            "fired": [asdict(r) | {"citation": r.citation} for r in ev.fired]}


@app.post("/api/rules/evaluate")
def evaluate_rules(fields: dict[str, Any]) -> dict[str, Any]:
    """Evaluate rule-pack fields directly (e.g. the workbook test cases)."""
    return _evaluation(evaluate_fields(fields))


@app.get("/api/projects/{pid}/rules")
def project_rules(p: Project = Depends(load)) -> dict[str, Any]:
    return _evaluation(evaluate_project(p)) | {"fields": project_fields(p)[0]}


@app.get("/api/projects")
def projects(st: ProjectStore = Depends(store)) -> list[dict[str, Any]]:
    return [{"id": p.id, "name": p.name, "stage": p.stage, "dnsp": p.get("site.dnsp"),
             "kva": p.get("calc.inverter_ac_kva")} for p in st.list()]


@app.post("/api/projects", status_code=201)
def create(body: CreateProject, st: ProjectStore = Depends(store)) -> dict[str, Any]:
    p = Project(name=body.name, delivery=Delivery() if body.engineering_delivery else None)
    p.log("user", "project.create", name=body.name)
    if body.brief:
        try:
            extraction = RuleExtractor().extract(body.brief)
            for field in extraction.fields:
                validate_parameter(field.key, field.value)
            apply_extraction(p, extraction)
        except (ValueError, TypeError, KeyError) as e:
            raise HTTPException(422, f"Project brief: {e}")
    refresh_design(p)
    return summary(st.save(p))


@app.get("/api/projects/{pid}")
def get_project(p: Project = Depends(load)) -> dict[str, Any]:
    return summary(p)


@app.delete("/api/projects/{pid}", status_code=204)
def delete_project(pid: str, st: ProjectStore = Depends(store)) -> Response:
    try:
        st.delete(pid)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "Project not found")
    return Response(status_code=204)


@app.post("/api/projects/{pid}/intake")
def intake(body: IntakeBody, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    try:
        res = RuleExtractor().extract(body.text)
        for field in res.fields:
            validate_parameter(field.key, field.value)
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(422, f"Additional information: {e}")
    written = apply_extraction(p, res, source_ref=body.source_ref)
    refresh_design(p)
    skipped = p.calculation_notes
    st.save(p)
    return {"extracted": [e.__dict__ for e in res.fields], "written": written, "calc_skipped": skipped,
            "project": summary(p)}


@app.put("/api/projects/{pid}/params/{key}")
def set_param(key: str, body: ParamBody, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    if key.startswith(("calc.", "rules.", "delivery.")):
        raise HTTPException(400, "calc.* / rules.* are produced by the calculation and rule engines and cannot be edited manually")
    if p.delivery is not None and p.delivery.design.equipment and key.startswith('equipment.'):
        raise HTTPException(409, 'Edit equipment in the Engineering delivery schedule; it owns the diagram and calculations')
    try:
        value = validate_parameter(key, body.value)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise HTTPException(422, str(e))
    p.set_param(key, value, Source(kind=SourceKind.USER_INPUT, ref=body.ref), unit=body.unit, actor=body.actor)
    refresh_design(p)
    st.save(p)
    return summary(p)


@app.put("/api/projects/{pid}/parameters")
def update_parameters(body: ParameterUpdates, p: Project = Depends(load), st: ProjectStore = Depends(store)):
    validated = []
    for update in body.updates:
        if p.delivery is not None and p.delivery.design.equipment and update.key.startswith('equipment.'):
            raise HTTPException(409, 'Edit equipment in the Engineering delivery schedule')
        if update.key.startswith(("calc.", "rules.", "delivery.")):
            raise HTTPException(400, "Calculated and rule parameters cannot be edited")
        if update.remove:
            import re
            if not re.fullmatch(r"[A-Za-z0-9_.]+", update.key):
                raise HTTPException(422, "Invalid parameter key")
            validated.append((update, None))
            continue
        try:
            validated.append((update, validate_parameter(update.key, update.value)))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise HTTPException(422, str(e))
    for update, value in validated:
        if update.remove:
            p.remove_param(update.key)
            continue
        p.set_param(update.key, value, Source(kind=SourceKind.USER_INPUT, ref=update.ref),
                    unit=update.unit, actor=update.actor)
    refresh_design(p)
    return summary(st.save(p))


@app.post("/api/projects/{pid}/params/{key}/confirm")
def confirm(key: str, body: ConfirmBody, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    if key not in p.params:
        raise HTTPException(404, "Parameter not found")
    p.confirm_param(key, body.engineer)
    st.save(p)
    return summary(p)


@app.post("/api/projects/{pid}/compute")
def compute(p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    refresh_design(p)
    skipped = p.calculation_notes
    if p.stage in (Stage.INTAKE, Stage.RULES) and not skipped:
        p.stage = Stage.COMPLIANCE
    st.save(p)
    return {"calc_skipped": skipped, "project": summary(p)}


@app.post("/api/projects/{pid}/bess")
def bess(p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    try:
        res = size_bess(p)
    except ValueError as e:
        raise HTTPException(400, str(e))
    st.save(p)
    return res


@app.post("/api/projects/{pid}/documents/generate")
def generate(only: list[str] | None = None, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    from ..delivery.documents import GENERATORS as delivery_generators
    known = set(GENERATORS) | (set(delivery_generators) if p.delivery is not None else set())
    if only is not None and (not only or any(doc_id not in known for doc_id in only)):
        raise HTTPException(422, "Select valid document IDs")
    p.calculation_notes = run_all(p)
    done, errors = generate_all(p, only)
    for doc_id in done:
        p.document_errors.pop(doc_id, None)
    p.document_errors.update(errors)
    if done and p.stage in (Stage.INTAKE, Stage.RULES, Stage.DESIGN, Stage.COMPLIANCE):
        p.stage = Stage.COMPLIANCE
    st.save(p)
    return {"generated": done, "errors": errors, "project": summary(p)}


@app.get("/api/projects/{pid}/documents/{doc_id}")
def document(doc_id: str, p: Project = Depends(load)) -> Response:
    d = p.documents.get(doc_id)
    if d is None:
        raise HTTPException(404, f"Document not found; available generators: {list(GENERATORS)}")
    return Response(d.content, media_type=f"{d.content_type}; charset=utf-8")


@app.get("/api/projects/{pid}/documents/{doc_id}/download")
def download_document(doc_id: str, p: Project = Depends(load)) -> Response:
    d = p.documents.get(doc_id)
    if d is None:
        raise HTTPException(404, "Document not found")
    if doc_id in p.stale_documents() or doc_id in p.document_errors:
        raise HTTPException(409, "Document is out of date; correct inputs and regenerate before downloading")
    return Response(d.content, media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="DRAFT_{d.filename}"'})


@app.post("/api/projects/{pid}/signoff")
def signoff(body: SignOff, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    try:
        p.sign(body)
    except ValueError as e:
        raise HTTPException(409, str(e))
    st.save(p)
    return summary(p)


@app.get("/api/projects/{pid}/package")
def package(mode: Literal["draft", "final"] = "draft", p: Project = Depends(load),
            st: ProjectStore = Depends(store)) -> Response:
    if mode == "final":
        raise HTTPException(409, "Use Engineering delivery to check and freeze a scoped final release; activate it first for legacy projects")
    try:
        data = build_package(p, mode)
    except PackageBlocked as e:
        raise HTTPException(409, {"message": "Final package requirements not met", "blockers": e.blockers})
    st.save(p)
    fname = f"{'DRAFT_' if mode == 'draft' else ''}GridEasy_{p.id}.zip"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/projects/{pid}/submitted")
def mark_submitted(p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    if p.delivery is not None:
        from ..delivery.readiness import complete_stage
        try:
            complete_stage(p, 'submission', p.delivery.design.milestones.submitted_by or 'employee')
        except ValueError as e:
            raise HTTPException(409, str(e))
    p.stage = Stage.SUBMITTED
    p.log("user", "project.submitted")
    st.save(p)
    return summary(p)


@app.post("/api/projects/{pid}/rfi")
def open_rfi(body: RfiBody, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    r = p.open_rfi(body.items)
    st.save(p)
    return {"round_no": r.round_no, "affected_documents": p.rfi_affected_documents(r.round_no), "project": summary(p)}


@app.post("/api/projects/{pid}/rfi/{round_no}/respond")
def respond_rfi(round_no: int, body: RfiRespond, p: Project = Depends(load), st: ProjectStore = Depends(store)) -> dict[str, Any]:
    if round_no < 1 or body.item_index < 0:
        raise HTTPException(404, "RFI item not found")
    try:
        r = p.rfi_rounds[round_no - 1]
        it = r.items[body.item_index]
    except IndexError:
        raise HTTPException(404, "RFI item not found")
    it.resolved, it.response = True, body.response
    p.log("user", "rfi.respond", round_no=round_no, item=body.item_index)
    if all(i.resolved for i in r.items):
        r.closed_at = now()
    st.save(p)
    return summary(p)

# Register modular engineering routes after the existing store/load/summary helpers.
from ..delivery.api import register as register_delivery
register_delivery(app, load, store, summary, refresh_design)
