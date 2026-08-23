# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Annotation workstation for the gold reference.

The reference is the slowest step and the one that decides whether anything
else means anything, so it gets a purpose-built tool rather than a shared
document: segment audio on a keypress, the policy rule card on screen, speaker
labels that persist across segments, and a save format the harness reads
directly.

Two annotators run this independently — different `--annotator` names, separate
output files — and neither sees the other's pass. Adjudication is a third run
over only the segments that disagree.

Usage:

    uv run task2-stt-benchmark/annotate/serve.py \\
        --manifest task2-stt-benchmark/data/manifest-rt1027.json \\
        --annotator ann1 \\
        --out task2-stt-benchmark/data/reference/pass-ann1.json

Stdlib only; binds to localhost.
"""
from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SEGMENT_ID = re.compile(r"^[A-Za-z0-9-]+$")


class State:
    def __init__(self, manifest_path: Path, annotator: str, out_path: Path):
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.annotator = annotator
        self.out_path = out_path
        self.segments = {s["id"]: s for s in self.manifest["segments"]}
        self.saved: dict[str, dict] = {}
        if out_path.exists():
            for entry in json.loads(out_path.read_text(encoding="utf-8")):
                self.saved[entry["segment_id"]] = entry

    def write(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = [
            self.saved[s["id"]]
            for s in self.manifest["segments"]
            if s["id"] in self.saved
        ]
        self.out_path.write_text(
            json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass  # keep the annotator's console usable

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/state":
                payload = {
                    "annotator": state.annotator,
                    "corpus_id": state.manifest["corpus_id"],
                    "segments": [
                        {"id": s["id"], "index": s["index"],
                         "start_s": s["start_s"], "end_s": s["end_s"],
                         "sha256": s["sha256"]}
                        for s in state.manifest["segments"]
                    ],
                    "saved": state.saved,
                    "policy": POLICY_CARD,
                }
                self._send(200, json.dumps(payload, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            elif path.startswith("/audio/"):
                segment_id = path[len("/audio/"):]
                # Path traversal guard: only ids the manifest actually contains,
                # and only after a shape check, so a crafted request cannot
                # reach outside the frozen segment directory.
                if not SEGMENT_ID.match(segment_id) or segment_id not in state.segments:
                    self._send(404, b"unknown segment", "text/plain")
                    return
                audio = Path(state.segments[segment_id]["path"])
                self._send(200, audio.read_bytes(), "audio/wav")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/save":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", "0"))
            entry = json.loads(self.rfile.read(length).decode("utf-8"))
            segment_id = entry.get("segment_id", "")
            if segment_id not in state.segments:
                self._send(400, b"unknown segment", "text/plain")
                return
            entry["annotator"] = state.annotator
            entry.setdefault("draft", {"kind": "none", "engine": "",
                                       "excluded_from_ranking": False, "note": ""})
            state.saved[segment_id] = entry
            state.write()
            self._send(200, json.dumps({"saved": len(state.saved)}).encode(),
                       "application/json")

    return Handler


POLICY_CARD = [
    ["R1", "Latin-script terms in Latin script: ClickHouse, never Кликхаус."],
    ["R2", "Vendor's own casing: OpenSearch, pgvector, LangChain."],
    ["R3", "Terms genuinely spoken as Russian stay Cyrillic: апи, деплой, прод, кубер."],
    ["R4", "Keep the English stem, write the Russian ending as heard: в ClickHouse-е, Kafkу."],
    ["R5", "Numerals as digits: «около трёхсот миллисекунд» -> около 300 миллисекунд."],
    ["R6", "Abbreviations unspaced: API, SLA, CI/CD, S3 — never «а п и»."],
    ["R7", "Fillers and false starts are transcribed: ну, вот, значит, «мы ре мы решили»."],
    ["R8", "Punctuation for readability; it is stripped before scoring."],
    ["R9", "[unintelligible] for what you cannot resolve. Never guess."],
    ["R10", "Speakers are S1, S2, … in order of first utterance, fixed for the whole corpus."],
    ["R11", "Do not type timestamps; they come from forced alignment."],
    ["R12", "Translation is not transcription: rollback stays rollback, never откат."],
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--annotator", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8731)
    args = parser.parse_args()

    state = State(args.manifest, args.annotator, args.out)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    print(f"annotating as {args.annotator}: http://127.0.0.1:{args.port}/")
    print(f"{len(state.saved)}/{len(state.segments)} segments already saved")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        state.write()
        print(f"\nsaved {len(state.saved)} segments to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
