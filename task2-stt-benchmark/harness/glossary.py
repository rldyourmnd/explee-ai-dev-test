"""Loader for the frozen IT-term glossary.

The glossary is data, not code, and it is frozen before scoring (see
`PREREGISTRATION.md`). `Glossary.fingerprint` is the SHA-256 of the file as it
was loaded, so a report can state which glossary produced its numbers and a
reader can check that it was not edited between freeze and publication.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .normalize import normalize_term, script_of

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "glossary.json"

# Kinds that count towards the separately reported product/vendor name recall.
NAME_KINDS = frozenset({"product", "vendor"})


@dataclass(frozen=True)
class Term:
    id: str
    canonical: str
    kind: str
    script: str
    variants: tuple[tuple[str, ...], ...]  # each variant as a token tuple
    note: str = ""

    @property
    def is_name(self) -> bool:
        return self.kind in NAME_KINDS


@dataclass(frozen=True)
class Glossary:
    terms: tuple[Term, ...]
    fingerprint: str
    frozen_at: str

    def __iter__(self):
        return iter(self.terms)

    def __len__(self) -> int:
        return len(self.terms)

    def by_id(self, term_id: str) -> Term:
        for term in self.terms:
            if term.id == term_id:
                return term
        raise KeyError(term_id)


def _variant_tokens(text: str) -> tuple[str, ...]:
    return tuple(normalize_term(text).split())


def load(path: Path | str = DEFAULT_PATH) -> Glossary:
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    terms = []
    for entry in data["terms"]:
        variants = tuple(_variant_tokens(v) for v in entry["accept"])
        if any(not v for v in variants):
            raise ValueError(f"term {entry['id']} has an empty accepted form")
        terms.append(
            Term(
                id=entry["id"],
                canonical=entry["canonical"],
                kind=entry["kind"],
                script=entry.get("script") or script_of(entry["canonical"]),
                variants=variants,
                note=entry.get("note", ""),
            )
        )
    ids = [t.id for t in terms]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate term id in glossary")
    return Glossary(
        terms=tuple(terms),
        fingerprint=hashlib.sha256(raw).hexdigest(),
        frozen_at=data.get("frozen_at", ""),
    )
