"""Levenshtein alignment over token sequences.

Every metric in this benchmark is derived from one alignment per segment, so
the alignment is computed once and shared. Keeping substitutions, deletions and
insertions as an explicit edit path is what makes the derived rates meaningful:
an omission and a hallucination are different failures, and WER alone hides
which one an engine committed.

Stdlib only; O(len(ref) * len(hyp)) time and memory. Segments are minutes of
speech, not hours, so the full matrix is affordable and exact — no beam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

Op = Literal["equal", "sub", "del", "ins"]


@dataclass(frozen=True)
class Edit:
    op: Op
    ref_index: int | None
    hyp_index: int | None


@dataclass(frozen=True)
class Alignment:
    ref: tuple[str, ...]
    hyp: tuple[str, ...]
    edits: tuple[Edit, ...]

    @property
    def hits(self) -> int:
        return sum(1 for e in self.edits if e.op == "equal")

    @property
    def substitutions(self) -> int:
        return sum(1 for e in self.edits if e.op == "sub")

    @property
    def deletions(self) -> int:
        return sum(1 for e in self.edits if e.op == "del")

    @property
    def insertions(self) -> int:
        return sum(1 for e in self.edits if e.op == "ins")

    @property
    def ref_length(self) -> int:
        return len(self.ref)

    def ref_to_hyp(self) -> dict[int, int | None]:
        """Map each reference index to the hypothesis index aligned to it.

        `None` means the reference token was deleted — nothing in the
        hypothesis stands where it should have been.
        """
        mapping: dict[int, int | None] = {}
        for edit in self.edits:
            if edit.ref_index is not None:
                mapping[edit.ref_index] = edit.hyp_index
        return mapping


def align(ref: Sequence[str], hyp: Sequence[str]) -> Alignment:
    """Exact minimum edit distance alignment with unit costs.

    Tie-breaking is fixed (substitution, then deletion, then insertion) so the
    alignment — and therefore every derived per-category count — is
    deterministic and reproducible across runs and machines.
    """
    n, m = len(ref), len(hyp)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    back: list[list[Op | None]] = [[None] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        cost[i][0] = i
        back[i][0] = "del"
    for j in range(1, m + 1):
        cost[0][j] = j
        back[0][j] = "ins"

    for i in range(1, n + 1):
        row, prev = cost[i], cost[i - 1]
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                row[j] = prev[j - 1]
                back[i][j] = "equal"
                continue
            sub, dele, ins = prev[j - 1] + 1, prev[j] + 1, row[j - 1] + 1
            best = min(sub, dele, ins)
            row[j] = best
            back[i][j] = "sub" if best == sub else ("del" if best == dele else "ins")

    edits: list[Edit] = []
    i, j = n, m
    while i > 0 or j > 0:
        op = back[i][j]
        if op in ("equal", "sub"):
            i, j = i - 1, j - 1
            edits.append(Edit(op, i, j))
        elif op == "del":
            i -= 1
            edits.append(Edit("del", i, None))
        else:
            j -= 1
            edits.append(Edit("ins", None, j))
    edits.reverse()
    return Alignment(tuple(ref), tuple(hyp), tuple(edits))


def find_ngram(sequence: Sequence[str], phrase: Sequence[str]) -> list[tuple[int, int]]:
    """All `[start, end)` spans where `phrase` occurs in `sequence`."""
    k = len(phrase)
    if k == 0 or k > len(sequence):
        return []
    return [
        (i, i + k)
        for i in range(len(sequence) - k + 1)
        if tuple(sequence[i : i + k]) == tuple(phrase)
    ]


def total(counts: Iterable[int]) -> int:
    return sum(counts)
