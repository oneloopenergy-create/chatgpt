"""Project single source of truth.

Design principles (see product doc, "Technical architecture"):
- Every parameter is stored once and must carry a Source; unsourced values never reach a final document.
- Every change bumps the parameter version and marks documents that reference it as stale.
- AI-extracted or default values are assumptions (needs_confirmation) until an engineer confirms them.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ConfigDict
from ..delivery.model import Delivery


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SourceKind(str, Enum):
    USER_INPUT = "user_input"          # entered manually in the UI
    DOCUMENT = "document_extract"      # extracted from uploaded files (bills, datasheets)
    BRIEF = "brief_extract"            # extracted from a free-text project brief
    RULE = "rule"                      # from a versioned rule pack
    CALCULATION = "calculation"        # deterministic calculation result
    ASSUMPTION = "assumption"          # system default assumption


class Source(BaseModel):
    kind: SourceKind
    ref: str = Field(..., min_length=1, description="Source locator, e.g. 'bill.pdf p2', 'rule:ausgrid@2026.1#export.static_limit_kw'")
    note: str | None = None


class Parameter(BaseModel):
    key: str
    value: Any
    unit: str | None = None
    source: Source
    version: int = 1
    updated_at: str = Field(default_factory=now)
    needs_confirmation: bool = False
    confirmed_by: str | None = None
    confirmed_at: str | None = None

    @property
    def is_assumption(self) -> bool:
        return self.needs_confirmation and self.confirmed_by is None


class DocStatus(str, Enum):
    DRAFT = "draft"
    STALE = "stale"      # a referenced parameter changed; regenerate
    SIGNED = "signed"    # signed off by a registered engineer


class Document(BaseModel):
    doc_id: str
    title: str
    filename: str
    content: str
    content_type: str = "text/plain"
    # parameters and versions used at generation time: {key: version}
    inputs: dict[str, int] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=now)
    status: DocStatus = DocStatus.DRAFT
    requires_signoff: bool = False
    todo: list[str] = Field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class SignOff(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reviewer_name: str = Field(min_length=1)
    registration_type: str = Field(..., min_length=1, description="RPEQ / NER / VIC-RBP etc.")
    registration_no: str = Field(min_length=1)
    scope: list[str] = Field(..., min_length=1, description="doc_ids covered by this review")
    doc_hashes: dict[str, str] = Field(default_factory=dict)
    signed_at: str = Field(default_factory=now)
    comment: str | None = None


class RfiItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field(min_length=1)
    affected_params: list[str] = Field(default_factory=list)
    resolved: bool = False
    response: str | None = None


class RfiRound(BaseModel):
    """A DNSP request-for-information (RFI) round."""
    round_no: int
    received_at: str = Field(default_factory=now)
    items: list[RfiItem] = Field(default_factory=list)
    closed_at: str | None = None


class AuditEntry(BaseModel):
    at: str = Field(default_factory=now)
    actor: str
    action: str
    detail: dict[str, Any] = Field(default_factory=dict)


class Stage(str, Enum):
    INTAKE = "1_intake"
    RULES = "2_rules"
    DESIGN = "3_design"
    COMPLIANCE = "4_compliance"
    PACKAGE = "5_package"
    SUBMITTED = "submitted"
    RFI = "rfi"
    OFFER = "offer"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    created_at: str = Field(default_factory=now)
    revision: int = 0
    stage: Stage = Stage.INTAKE
    params: dict[str, Parameter] = Field(default_factory=dict)
    documents: dict[str, Document] = Field(default_factory=dict)
    signoffs: list[SignOff] = Field(default_factory=list)
    rfi_rounds: list[RfiRound] = Field(default_factory=list)
    audit: list[AuditEntry] = Field(default_factory=list)

    delivery: Delivery | None = None

    calculation_notes: list[str] = Field(default_factory=list)
    document_errors: dict[str, str] = Field(default_factory=dict)

    # ------------------------------------------------------------------ params
    def get(self, key: str, default: Any = None) -> Any:
        p = self.params.get(key)
        return p.value if p is not None else default

    def set_param(
        self,
        key: str,
        value: Any,
        source: Source,
        *,
        unit: str | None = None,
        actor: str = "system",
        needs_confirmation: bool | None = None,
    ) -> Parameter:
        if needs_confirmation is None:
            needs_confirmation = source.kind in (SourceKind.BRIEF, SourceKind.DOCUMENT, SourceKind.ASSUMPTION)
        old = self.params.get(key)
        effective_unit = unit if unit is not None else (old.unit if old else None)
        if old is not None and old.value == value and old.unit == effective_unit and old.source == source:
            return old
        version = (old.version + 1) if old else 1
        p = Parameter(
            key=key, value=value, unit=unit if unit is not None else (old.unit if old else None),
            source=source, version=version, needs_confirmation=needs_confirmation,
        )
        self.params[key] = p
        stale = self._mark_dependents_stale(key)
        self.log(actor, "param.set", key=key, value=value, version=version,
                 source=source.model_dump(mode="json"), stale_docs=stale)
        return p

    def remove_param(self, key: str) -> None:
        if key not in self.params:
            return
        del self.params[key]
        stale = []
        for doc in self.documents.values():
            if key in doc.inputs:
                doc.status = DocStatus.STALE
                stale.append(doc.doc_id)
        self.log("system", "param.remove", key=key, stale_docs=stale)

    def confirm_param(self, key: str, engineer: str) -> Parameter:
        p = self.params[key]
        p.confirmed_by = engineer
        p.confirmed_at = now()
        self.log(engineer, "param.confirm", key=key, version=p.version)
        return p

    def assumptions(self) -> list[Parameter]:
        """Explicit list of assumptions awaiting engineer confirmation."""
        return [p for p in self.params.values() if p.is_assumption]

    # --------------------------------------------------------------- documents
    def _mark_dependents_stale(self, key: str) -> list[str]:
        stale = []
        for d in self.documents.values():
            if key in d.inputs and d.inputs[key] != self.params[key].version and d.status != DocStatus.STALE:
                d.status = DocStatus.STALE
                stale.append(d.doc_id)
        return stale

    def put_document(self, doc: Document, actor: str = "system") -> Document:
        prev = self.documents.get(doc.doc_id)
        if prev is not None and prev.sha256 == doc.sha256 and prev.status == DocStatus.SIGNED:
            # content unchanged: keep the sign-off
            doc.status = DocStatus.SIGNED
        self.documents[doc.doc_id] = doc
        self.log(actor, "doc.generate", doc_id=doc.doc_id, sha256=doc.sha256[:12], inputs=doc.inputs)
        return doc

    def stale_documents(self) -> list[str]:
        out = []
        for d in self.documents.values():
            if d.status == DocStatus.STALE:
                out.append(d.doc_id)
                continue
            for k, v in d.inputs.items():
                p = self.params.get(k)
                if (p.version if p else 0) != v:
                    out.append(d.doc_id)
                    break
        return out

    # ----------------------------------------------------------------- signoff
    def sign(self, s: SignOff) -> SignOff:
        missing = [d for d in s.scope if d not in self.documents]
        if missing:
            raise ValueError(f"Sign-off scope includes unknown documents: {missing}")
        stale = set(self.stale_documents()) & set(s.scope)
        if stale:
            raise ValueError(f"Stale documents cannot be signed off: {sorted(stale)}")
        s.doc_hashes = {d: self.documents[d].sha256 for d in s.scope}
        for d in s.scope:
            self.documents[d].status = DocStatus.SIGNED
        self.signoffs.append(s)
        self.log(s.reviewer_name, "doc.signoff", registration=f"{s.registration_type} {s.registration_no}",
                 scope=s.scope)
        return s

    def is_signed(self, doc_id: str) -> bool:
        d = self.documents.get(doc_id)
        if d is None or doc_id in self.stale_documents():
            return False
        return any(s.doc_hashes.get(doc_id) == d.sha256 for s in self.signoffs)

    # --------------------------------------------------------------------- rfi
    def open_rfi(self, items: list[RfiItem], actor: str = "user") -> RfiRound:
        r = RfiRound(round_no=len(self.rfi_rounds) + 1, items=items)
        self.rfi_rounds.append(r)
        self.stage = Stage.RFI
        self.log(actor, "rfi.open", round_no=r.round_no, items=len(items))
        return r

    def rfi_affected_documents(self, round_no: int) -> list[str]:
        """RFI impact analysis: documents that reference the queried parameters."""
        r = self.rfi_rounds[round_no - 1]
        keys = {k for it in r.items for k in it.affected_params}
        return sorted(d.doc_id for d in self.documents.values() if keys & set(d.inputs))

    # ------------------------------------------------------------------- audit
    def log(self, actor: str, action: str, **detail: Any) -> None:
        self.audit.append(AuditEntry(actor=actor, action=action, detail=json.loads(json.dumps(detail, default=str))))
