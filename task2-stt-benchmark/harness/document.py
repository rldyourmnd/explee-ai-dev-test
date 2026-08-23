"""Scoring a whole-document reference against per-segment engine output.

The publisher's transcript is one continuous text with no timestamps, while
each engine returns 99 separate segments. Something has to line them up, and
the obvious approach — one exact Levenshtein alignment over ~5 000 × ~5 000
tokens — needs a 25-million-cell matrix per engine, which this machine does not
have to spare.

So alignment is anchored instead. Tokens that occur exactly once in the
reference and exactly once in the hypothesis are unambiguous tie points; keeping
only the monotone increasing subset of those gives a skeleton, and positions
between anchors are interpolated. Exact alignment then runs *inside* each small
block, where it is cheap and still exact.

The blocks are defined on the **reference**, at fixed token counts, so every
engine is scored on the same units and the paired bootstrap has something to
pair. An engine that drifts is penalised inside its blocks, not by getting
different blocks.

Stdlib only.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from typing import Sequence

from .glossary import Glossary
from .metrics import SegmentScore, Transcript, score_segment
from .normalize import tokens

#: Reference tokens per scoring block. ~50 tokens is roughly a segment's worth
#: of speech, giving ~99 blocks over this corpus — enough units for a bootstrap
#: without making any single block too short to score.
BLOCK_TOKENS = 50


def unique_anchors(ref: Sequence[str], hyp: Sequence[str]) -> list[tuple[int, int]]:
    """Monotone tie points: tokens occurring exactly once on both sides."""
    ref_counts, hyp_counts = Counter(ref), Counter(hyp)
    ref_pos = {t: i for i, t in enumerate(ref) if ref_counts[t] == 1}
    hyp_pos = {t: j for j, t in enumerate(hyp) if hyp_counts[t] == 1}
    shared = sorted(
        (ref_pos[t], hyp_pos[t]) for t in ref_pos.keys() & hyp_pos.keys()
    )
    # Longest increasing subsequence on the hypothesis index: an anchor that
    # goes backwards is a coincidental repeat, not a real correspondence.
    tails: list[int] = []
    parents: list[int | None] = []
    index: list[int] = []
    for k, (_, j) in enumerate(shared):
        pos = bisect_left(tails, j)
        if pos == len(tails):
            tails.append(j)
            index.append(k)
        else:
            tails[pos] = j
            index[pos] = k
        parents.append(index[pos - 1] if pos else None)
    if not tails:
        return []
    chain: list[tuple[int, int]] = []
    k: int | None = index[len(tails) - 1]
    while k is not None:
        chain.append(shared[k])
        k = parents[k]
    chain.reverse()
    return chain


def _projector(anchors: Sequence[tuple[int, int]], ref_len: int, hyp_len: int):
    """Map a reference index to a hypothesis index by interpolation."""
    if not anchors:
        scale = (hyp_len / ref_len) if ref_len else 0.0
        return lambda i: min(hyp_len, max(0, round(i * scale)))

    ref_points = [a for a, _ in anchors]

    def project(i: int) -> int:
        pos = bisect_left(ref_points, i)
        if pos == 0:
            a_ref, a_hyp = anchors[0]
            return max(0, a_hyp - (a_ref - i))
        if pos >= len(anchors):
            a_ref, a_hyp = anchors[-1]
            return min(hyp_len, a_hyp + (i - a_ref))
        left_ref, left_hyp = anchors[pos - 1]
        right_ref, right_hyp = anchors[pos]
        span = right_ref - left_ref
        if span <= 0:
            return left_hyp
        ratio = (i - left_ref) / span
        return int(round(left_hyp + ratio * (right_hyp - left_hyp)))

    return project


def score_document(
    engine: str,
    reference_text: str,
    hypothesis_text: str,
    glossary: Glossary,
    block_tokens: int = BLOCK_TOKENS,
) -> list[SegmentScore]:
    """Score one engine's full transcript against the document reference.

    Returns one `SegmentScore` per reference block, with block ids that are
    identical across engines so the paired bootstrap can pair them.
    """
    ref = tokens(reference_text)
    hyp = tokens(hypothesis_text)
    project = _projector(unique_anchors(ref, hyp), len(ref), len(hyp))

    scores: list[SegmentScore] = []
    for start in range(0, len(ref), block_tokens):
        end = min(start + block_tokens, len(ref))
        block_id = f"blk-{start // block_tokens:04d}"
        h_start, h_end = project(start), project(end)
        if h_end < h_start:
            h_start, h_end = h_end, h_start
        scores.append(
            score_segment(
                block_id,
                engine,
                Transcript(" ".join(ref[start:end])),
                Transcript(" ".join(hyp[h_start:h_end])),
                glossary,
            )
        )
    return scores
