"""Packaging: bundle documents in the order the DNSP requires.

- draft mode: available any time; file names get a DRAFT_ prefix and the manifest lists all blockers.
- final mode: requires no error-level findings, verified rule packs, no unconfirmed assumptions, no stale
  documents, and every document that needs sign-off signed by a registered engineer (content unchanged since).
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Literal

from ..compliance.checks import run_checks
from ..core.model import Project, Stage
from ..rules.library import load_pack


class PackageBlocked(Exception):
    def __init__(self, blockers: list[str]):
        super().__init__("; ".join(blockers))
        self.blockers = blockers


def blockers(p: Project) -> list[str]:
    out = [f"[{f.id}] {f.title}" for f in run_checks(p) if f.severity == "error" or f.id == "rules.unverified"]
    if p.assumptions():
        out.append(f"{len(p.assumptions())} assumption(s) not confirmed")
    from .documents import GENERATORS
    for doc_id in GENERATORS:
        if doc_id not in p.documents:
            out.append(f"Required document missing: {doc_id}")
    for doc_id in p.stale_documents():
        out.append(f"Document requires regeneration: {doc_id}")
    for d in p.documents.values():
        if d.todo:
            out.append(f"{d.title}: {len(d.todo)} unresolved review item(s)")
        if d.requires_signoff and not p.is_signed(d.doc_id):
            out.append(f"{d.title} not signed off by a registered engineer")
    return out


def build_package(p: Project, mode: Literal["draft", "final"] = "draft", actor: str = "user") -> bytes:
    blk = blockers(p)
    if mode == "final" and blk:
        raise PackageBlocked(blk)
    order = load_pack(p.get("rules.dnsp_pack"))["package_order"] if p.get("rules.dnsp_pack") else []
    docs = sorted(p.documents.values(), key=lambda d: (order.index(d.doc_id) if d.doc_id in order else 99, d.filename))
    prefix = "" if mode == "final" else "DRAFT_"
    manifest = {
        "project": p.name, "project_id": p.id, "mode": mode, "dnsp_rule_pack": p.get("rules.dnsp_pack"),
        "documents": [{"file": prefix + d.filename, "title": d.title, "sha256": d.sha256,
                       "signed": p.is_signed(d.doc_id), "todo": d.todo, "inputs": d.inputs} for d in docs],
        "signoffs": [s.model_dump() for s in p.signoffs],
        "blockers": blk,
        "disclaimer": "GridEasy produces drafts only; sign-off and submission are by the customer's registered engineer.",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in docs:
            z.writestr(prefix + d.filename, d.content)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    if mode == "final":
        p.stage = Stage.PACKAGE
    p.log(actor, "package.build", mode=mode, blockers=len(blk))
    return buf.getvalue()
