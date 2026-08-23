"""Corpus freezing: one authorised source file, one segment manifest.

Fairness in this benchmark is mechanical, not a promise. Every engine is sent
byte-identical segment files, produced once by this module with one declared
`ffmpeg` invocation. No adapter is allowed to resample, re-cut, or re-channel
its own copy — if an engine needs a different container, it converts *from the
frozen segment* and records the conversion, so the difference is visible.

Everything is keyed by SHA-256: the source file, each segment, and the manifest
itself. A published report can therefore be checked: same hashes, same corpus.

`ffmpeg`/`ffprobe` are invoked as external tools. Their absence is a hard error
with a readable message rather than a silent fallback to a different pipeline.

Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

# Declared once, applied to every engine. 16 kHz mono PCM is the lowest common
# denominator every vendor accepts natively, so no engine gets a private
# re-encode that the others did not receive.
TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1
TARGET_CODEC = "pcm_s16le"
SEGMENT_SUFFIX = ".wav"


class ToolMissing(RuntimeError):
    pass


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ToolMissing(
            f"{tool} is required to freeze the corpus and was not found on PATH. "
            "Install it rather than substituting another decoder: a different "
            "decoder would give a different corpus than the published hashes."
        )
    return path


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AudioProperties:
    duration_s: float
    sample_rate: int
    channels: int
    codec: str
    format_name: str


def probe(path: Path | str) -> AudioProperties:
    """Read real audio properties. Nothing here is assumed from the filename."""
    ffprobe = _require("ffprobe")
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", "-select_streams", "a:0", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    if not data.get("streams"):
        raise ValueError(f"{path} has no audio stream")
    stream = data["streams"][0]
    fmt = data.get("format", {})
    duration = stream.get("duration") or fmt.get("duration")
    return AudioProperties(
        duration_s=float(duration),
        sample_rate=int(stream["sample_rate"]),
        channels=int(stream["channels"]),
        codec=str(stream["codec_name"]),
        format_name=str(fmt.get("format_name", "")),
    )


@dataclass(frozen=True)
class Segment:
    id: str
    index: int
    start_s: float
    end_s: float
    sha256: str
    path: str

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class Manifest:
    corpus_id: str
    source_path: str
    source_sha256: str
    source_properties: AudioProperties
    segments: list[Segment]
    target_sample_rate: int = TARGET_SAMPLE_RATE
    target_channels: int = TARGET_CHANNELS
    target_codec: str = TARGET_CODEC
    created_at: str = ""
    speaker_count: int | None = None
    provenance: str = ""
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["segment_count"] = len(self.segments)
        payload["total_segment_duration_s"] = round(
            sum(s.duration_s for s in self.segments), 3
        )
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    def fingerprint(self) -> str:
        return sha256_text(self.to_json())

    def write(self, path: Path | str) -> str:
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")
        return self.fingerprint()

    @classmethod
    def load(cls, path: Path | str) -> "Manifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.pop("segment_count", None)
        data.pop("total_segment_duration_s", None)
        data["source_properties"] = AudioProperties(**data["source_properties"])
        data["segments"] = [Segment(**s) for s in data["segments"]]
        return cls(**data)


def fixed_boundaries(
    duration_s: float, segment_s: float = 30.0, minimum_s: float = 5.0
) -> list[tuple[float, float]]:
    """Uniform cut points.

    Uniform, not silence-based, because a voice-activity cut would place the
    boundaries differently for different audio and make the segment count an
    artefact of the tool. A final fragment shorter than `minimum_s` is merged
    into its predecessor so no engine is billed a minimum charge for a scrap of
    audio nobody scores.
    """
    if duration_s <= 0:
        return []
    bounds: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_s:
        end = min(start + segment_s, duration_s)
        bounds.append((round(start, 3), round(end, 3)))
        start = end
    if len(bounds) > 1 and (bounds[-1][1] - bounds[-1][0]) < minimum_s:
        last = bounds.pop()
        bounds[-1] = (bounds[-1][0], last[1])
    return bounds


def cut_segments(
    source: Path | str,
    out_dir: Path | str,
    boundaries: Sequence[tuple[float, float]],
    *,
    corpus_id: str,
) -> list[Segment]:
    """Cut the frozen segment files that every engine will receive."""
    ffmpeg = _require("ffmpeg")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    segments: list[Segment] = []
    for index, (start, end) in enumerate(boundaries):
        segment_id = f"{corpus_id}-{index:04d}"
        target = out / f"{segment_id}{SEGMENT_SUFFIX}"
        subprocess.run(
            [
                ffmpeg, "-nostdin", "-y", "-v", "error",
                "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
                "-ac", str(TARGET_CHANNELS), "-ar", str(TARGET_SAMPLE_RATE),
                "-c:a", TARGET_CODEC, str(target),
            ],
            check=True, capture_output=True,
        )
        segments.append(
            Segment(
                id=segment_id,
                index=index,
                start_s=start,
                end_s=end,
                sha256=sha256_file(target),
                path=str(target),
            )
        )
    return segments


def freeze(
    source: Path | str,
    out_dir: Path | str,
    *,
    corpus_id: str,
    provenance: str,
    segment_s: float = 30.0,
    speaker_count: int | None = None,
    notes: Sequence[str] = (),
) -> Manifest:
    """Freeze one authorised source file into a hashed segment manifest.

    `provenance` is required and free text: who authorised this audio, and
    under what constraint. An unattributed corpus is not usable evidence.
    """
    if not provenance.strip():
        raise ValueError("provenance is required: record who authorised this audio")
    source = Path(source)
    properties = probe(source)
    boundaries = fixed_boundaries(properties.duration_s, segment_s=segment_s)
    segments = cut_segments(source, out_dir, boundaries, corpus_id=corpus_id)
    return Manifest(
        corpus_id=corpus_id,
        source_path=str(source),
        source_sha256=sha256_file(source),
        source_properties=properties,
        segments=segments,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        speaker_count=speaker_count,
        provenance=provenance,
        notes=list(notes),
    )
