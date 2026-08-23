# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Reference-free analysis of the stored engine output.

No gold reference could be obtained (see `docs/reference-protocol.md` and the
report), so no authoritative ranking is published. What *can* be measured
without ground truth is measured here, and each number is labelled with what it
does and does not license:

* **Pairwise disagreement** — how far apart two engines are, in the same WER
  units the ranking would have used. Symmetric and reference-free.
* **Leave-one-out consensus** — each engine scored against the agreement of the
  *other* engines. Not gold: it favours whichever engine resembles the
  majority, and it is blind to errors every engine makes. Reported as a proxy,
  never as accuracy.
* **Glossary-term production** — how often each engine emits each frozen term.
  This needs no reference at all, and it is the axis the employer complained
  about: an engine that never produces `ClickHouse` anywhere in an hour of a
  ClickHouse-heavy conversation is telling us something real.
* **Latin-to-Cyrillic mangling at consensus term sites** — where the other
  engines agree a Latin term was spoken, what did this engine write instead?
  That is the `РАКа` failure, measured directly.

Stdlib only. Writes `data/analysis.json`.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness.align import align  # noqa: E402
from harness.glossary import load as load_glossary  # noqa: E402
from harness.metrics import Transcript, token_stream  # noqa: E402
from harness.normalize import script_of, tokens  # noqa: E402

RAW = HERE / "data" / "raw"
MANIFEST = HERE / "data" / "manifest-rt1027.json"


def load_engine_outputs() -> dict[str, dict[str, str]]:
    """`engine -> segment_id -> text`, straight from stored raw output."""
    engines: dict[str, dict[str, str]] = {}
    for engine_dir in sorted(RAW.iterdir()):
        if not engine_dir.is_dir():
            continue
        texts: dict[str, str] = {}
        for path in sorted(engine_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            texts[payload["segment_id"]] = payload.get("text", "")
        if texts:
            engines[engine_dir.name] = texts
    return engines


def pairwise_disagreement(engines: dict[str, dict[str, str]]) -> list[dict]:
    """Pooled token disagreement between every pair, over shared segments."""
    rows = []
    names = sorted(engines)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = sorted(set(engines[a]) & set(engines[b]))
            edits = ref_words = 0
            for segment_id in shared:
                left, right = tokens(engines[a][segment_id]), tokens(engines[b][segment_id])
                alignment = align(left, right)
                edits += (
                    alignment.substitutions + alignment.deletions + alignment.insertions
                )
                ref_words += len(left)
            rows.append({
                "a": a, "b": b, "segments": len(shared),
                "disagreement": round(edits / ref_words, 4) if ref_words else None,
            })
    return rows


def term_production(engines: dict[str, dict[str, str]], glossary) -> dict:
    """How many times each engine produced each glossary term."""
    counts: dict[str, Counter] = {}
    for engine, texts in engines.items():
        counter: Counter = Counter()
        for text in texts.values():
            stream = token_stream(Transcript(text))
            for term in glossary:
                for variant in term.variants:
                    k = len(variant)
                    hits = sum(
                        1 for i in range(len(stream.terms) - k + 1)
                        if tuple(stream.terms[i:i + k]) == variant
                    )
                    if hits:
                        counter[term.id] += hits
        counts[engine] = counter
    return {
        "per_engine": {e: dict(c) for e, c in counts.items()},
        "totals": dict(sum(counts.values(), Counter())),
    }


def consensus_term_sites(engines: dict[str, dict[str, str]], glossary) -> dict:
    """Where a majority of engines agree a Latin term occurred, who dissents?

    A site is a (segment, term) pair produced by at least two engines. For the
    engines that did *not* produce it there, we record whether they wrote
    Cyrillic in that segment at all — the `РАКа` shape — but we cannot know
    what was truly said, so this is evidence, not a verdict.
    """
    names = sorted(engines)
    if len(names) < 3:
        return {"note": "needs at least three engines", "sites": []}

    produced: dict[tuple[str, str], set[str]] = defaultdict(set)
    for engine, texts in engines.items():
        for segment_id, text in texts.items():
            stream = token_stream(Transcript(text))
            for term in glossary:
                if term.script != "latin":
                    continue
                for variant in term.variants:
                    k = len(variant)
                    if any(
                        tuple(stream.terms[i:i + k]) == variant
                        for i in range(len(stream.terms) - k + 1)
                    ):
                        produced[(segment_id, term.id)].add(engine)
                        break

    majority = (len(names) // 2) + 1
    misses: Counter = Counter()
    sites = 0
    examples: list[dict] = []
    for (segment_id, term_id), who in sorted(produced.items()):
        if len(who) < majority:
            continue
        sites += 1
        for engine in names:
            if engine in who:
                continue
            misses[engine] += 1
            if len(examples) < 12:
                examples.append({
                    "segment": segment_id, "term": term_id, "missed_by": engine,
                    "agreed_by": sorted(who),
                    "text": engines[engine].get(segment_id, "")[:180],
                })
    return {
        "consensus_sites": sites,
        "majority_threshold": majority,
        "misses_per_engine": dict(misses),
        "examples": examples,
    }


def script_mix(engines: dict[str, dict[str, str]]) -> dict:
    """Share of Latin-script tokens each engine emits.

    A Russian-only engine transcribing a code-switched conversation has to put
    the English terms *somewhere*; if it emits almost no Latin script, it is
    transliterating them into Cyrillic, which is the reported failure.
    """
    out = {}
    for engine, texts in engines.items():
        counter: Counter = Counter()
        for text in texts.values():
            for token in tokens(text):
                counter[script_of(token)] += 1
        total = sum(counter.values())
        out[engine] = {
            "tokens": total,
            "latin_share": round(counter["latin"] / total, 5) if total else None,
            "cyrillic_share": round(counter["cyrillic"] / total, 5) if total else None,
        }
    return out


def main() -> int:
    glossary = load_glossary()
    engines = load_engine_outputs()
    if not engines:
        print("no stored engine output found", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    analysis = {
        "corpus": {
            "id": manifest["corpus_id"],
            "source_sha256": manifest["source_sha256"],
            "segments": len(manifest["segments"]),
            "window": manifest.get("window"),
            "manifest_segments_total_s": manifest.get("total_segment_duration_s"),
        },
        "glossary_fingerprint": glossary.fingerprint,
        "engines": {
            e: {"segments": len(t), "empty": sum(1 for x in t.values() if not x.strip())}
            for e, t in sorted(engines.items())
        },
        "pairwise_disagreement": pairwise_disagreement(engines),
        "term_production": term_production(engines, glossary),
        "consensus_term_sites": consensus_term_sites(engines, glossary),
        "script_mix": script_mix(engines),
    }
    out = HERE / "data" / "analysis.json"
    out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(analysis["engines"], ensure_ascii=False, indent=2))
    print("pairwise:", json.dumps(analysis["pairwise_disagreement"], ensure_ascii=False))
    print("script mix:", json.dumps(analysis["script_mix"], ensure_ascii=False))
    print("consensus sites:", analysis["consensus_term_sites"]["consensus_sites"],
          analysis["consensus_term_sites"]["misses_per_engine"])
    print("top terms:", Counter(analysis["term_production"]["totals"]).most_common(12))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
