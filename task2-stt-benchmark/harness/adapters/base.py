"""The per-engine adapter interface.

One interface, so that adding an engine is a file and not a change to the
runner, and so a missing credential blocks exactly one adapter instead of the
run. Three properties are enforced here rather than left to each vendor
integration:

* **Raw first.** An adapter returns the vendor's response untouched
  (`EngineResult.raw`) plus a parse into the common shape. Scoring reads the
  parse; the report publishes the hash of the raw. Nothing is normalised before
  it has been stored.
* **Credentials from the environment only.** `api_key_env` names a variable;
  the adapter reads it through `require_key`, which never returns the value to
  the caller's logs and never puts it in a repr. Traces from this repository
  are published verbatim (AGENTS.md rule 2).
* **The declared configuration is data.** `model_id`, `snapshot_date` and every
  request parameter are recorded on the result, because "we used Nova-3" is not
  reproducible and a marketing price is not a measurement.

Adapters come in two variants of the same engine where the vendor supports it:
`track="default"` (stock model, no terminology help) and `track="tuned"`
(glossary / keyterm prompting). They are ranked separately and never mixed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from ..metrics import Transcript

TRACKS = ("default", "tuned")


class MissingCredential(RuntimeError):
    """Raised when an adapter's environment variable is absent."""


def require_key(env_name: str) -> str:
    """Fetch a credential from the environment, or fail loudly.

    The value is returned to the caller and must go straight into a request
    header. It is never logged, never formatted into a message, and never
    stored on a dataclass that gets serialised.
    """
    value = os.environ.get(env_name)
    if not value:
        raise MissingCredential(
            f"environment variable {env_name} is not set; this adapter is skipped"
        )
    return value


@dataclass
class EngineResult:
    """One engine's answer for one segment, with its cost of being obtained."""

    engine: str
    track: str
    segment_id: str
    model_id: str
    snapshot_date: str
    request_params: dict[str, Any]
    raw: str
    raw_sha256: str = ""
    transcript: Transcript = field(default_factory=Transcript)
    latency_s: float | None = None
    retries: int = 0
    billed_usd: float | None = None
    billed_source: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Adapter(Protocol):
    """What every engine integration must provide."""

    name: str
    track: str
    model_id: str
    snapshot_date: str
    api_key_env: str

    def request_params(self, glossary_terms: Sequence[str]) -> dict[str, Any]:
        """Exact parameters sent with each request, for the record."""
        ...

    def available(self) -> bool:
        """True when this adapter's credential is present."""
        ...

    def transcribe(self, segment_path: str, glossary_terms: Sequence[str]) -> EngineResult:
        """Transcribe one frozen segment file. Must not re-cut or resample it."""
        ...


@dataclass
class BaseAdapter:
    """Shared behaviour; vendor subclasses implement `_call` and `_parse`."""

    name: str = "base"
    track: str = "default"
    model_id: str = ""
    snapshot_date: str = ""
    api_key_env: str = ""
    #: Vendors that support terminology hints set this; those that do not keep
    #: it False and the report says so rather than showing an empty tuned row.
    supports_terminology: bool = False

    def request_params(self, glossary_terms: Sequence[str]) -> dict[str, Any]:
        params: dict[str, Any] = {"model": self.model_id, "language": "ru"}
        if self.track == "tuned" and self.supports_terminology:
            params["keyterms"] = list(glossary_terms)
        return params

    def available(self) -> bool:
        return bool(os.environ.get(self.api_key_env))

    def transcribe(self, segment_path: str, glossary_terms: Sequence[str]) -> EngineResult:
        raise NotImplementedError(
            f"{self.name}: no vendor call is implemented yet. Adapters are wired "
            "only after the human authorises the audio source and the spend "
            "ceiling; until then this raises instead of quietly returning empty "
            "text that would score as a perfect omission-free failure."
        )
