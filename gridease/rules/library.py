"""Versioned rule library: ENA guidelines, AS/NZS 4777.2, DNSP technical standards and application forms.

Each pack carries id / version / verified. When a rule value is written into a project its source is
recorded as ``rule:<pack_id>@<version>#<path>`` for traceability and impact analysis on rule updates.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACK_DIR = Path(__file__).parent / "packs"

DNSP_IDS = {
    "ausgrid": "dnsp_ausgrid",
    "endeavour": "dnsp_endeavour",
    "endeavour energy": "dnsp_endeavour",
    "essential": "dnsp_essential",
    "essential energy": "dnsp_essential",
    "energex": "dnsp_energex",
    "ergon": "dnsp_ergon",
    "ergon energy": "dnsp_ergon",
    "ergon energy network": "dnsp_ergon",
    "energex limited": "dnsp_energex",
}


class RulePack(dict):
    @property
    def ref(self) -> str:
        return f"rule:{self['id']}@{self['version']}"

    def at(self, path: str) -> tuple[Any, str]:
        """Look up a dotted path; returns (value, source ref)."""
        node: Any = self
        for part in path.split("."):
            node = node[part]
        return node, f"{self.ref}#{path}"


@lru_cache(maxsize=None)
def load_pack(pack_id: str) -> RulePack:
    path = PACK_DIR / f"{pack_id}.yaml"
    if not path.exists():
        raise KeyError(f"Unknown rule pack: {pack_id}")
    pack = yaml.safe_load(path.read_text(encoding="utf-8"))
    # shared rule files (e.g. STNW1175 for both Energex and Ergon) are merged in
    for inc in pack.pop("include", []) or []:
        shared = yaml.safe_load((PACK_DIR / f"{inc}.yaml").read_text(encoding="utf-8"))
        pack.setdefault("sources", {}).update(shared.get("sources", {}))
        pack.setdefault("rules", []).extend(shared.get("rules", []))
    return RulePack(pack)


def list_packs() -> list[dict[str, Any]]:
    out = []
    for f in sorted(PACK_DIR.glob("*.yaml")):
        if f.stem.startswith("shared_"):
            continue
        p = load_pack(f.stem)
        out.append({k: p.get(k) for k in ("id", "title", "version", "verified", "source")})
    return out


def dnsp_pack(dnsp: str) -> RulePack:
    key = dnsp.strip().lower()
    pid = DNSP_IDS.get(key) or (key if key.startswith("dnsp_") else None)
    if pid is None:
        raise KeyError(f"DNSP not supported in the MVP: {dnsp} (currently NSW / QLD major DNSPs)")
    return load_pack(pid)


def find_cec_inverter(manufacturer: str, model: str) -> dict[str, Any] | None:
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())  # noqa: E731
    for inv in load_pack("cec_inverters")["inverters"]:
        if norm(inv["manufacturer"]) == norm(manufacturer) and norm(inv["model"]) == norm(model):
            return inv
    return None
