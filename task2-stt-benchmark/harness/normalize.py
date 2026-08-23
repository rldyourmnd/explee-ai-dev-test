"""Text normalisation for scoring.

Two levels, kept separate on purpose:

* `normalize_for_wer` — the *only* transformation applied before word-error
  scoring. It is deliberately shallow: case, punctuation, `ё`, whitespace and
  hyphen handling. It never rewrites a word into another word, because a
  normaliser that maps `РАКа` onto `rag` would erase exactly the failure the
  employer asked us to catch.
* `normalize_term` — the same shallow pass plus Russian inflectional-suffix
  stripping, used only when deciding whether a *glossary term* was recognised.
  `в ClickHouse` and `в ClickHouse-е` are the same term; `Lead House` is not.

Normalisation is applied identically to every engine's output and to the
reference, and it is applied to raw stored output — never in place of it.

Stdlib only.
"""
from __future__ import annotations

import re
import unicodedata

# Characters we drop entirely before tokenising. Sentence punctuation carries no
# lexical content for WER; the reference policy scores punctuation separately.
_PUNCT = re.compile(r"[^\w\s\-]", re.UNICODE)
_WS = re.compile(r"\s+", re.UNICODE)

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN = re.compile(r"[A-Za-z]")

# Inflectional tails that Russian grammar attaches to a Latin-script noun, with
# or without a hyphen: `ClickHouse-е`, `Workerа`, `RAG-ом`, `Kafkaй`.
_RU_TAIL = re.compile(
    r"(?:[-‑]?(?:ами|ями|ого|ему|ому|ых|их|ам|ям|ах|ях|ов|ев|ей|ом|ем|"
    r"е|у|ю|ы|и|а|я|о|ой|ей))$"
)


def fold(text: str) -> str:
    """Case-fold, unify `ё`→`е`, NFC-normalise. Reversible enough to audit."""
    text = unicodedata.normalize("NFC", text)
    return text.casefold().replace("ё", "е").replace("Ё", "е")


def normalize_for_wer(text: str) -> str:
    """Shallow scoring normalisation. Returns a space-joined token string."""
    text = fold(text)
    # A hyphen inside a word is a token boundary (`RAG-пайплайн` -> two tokens)
    # so that a hyphenation disagreement is not scored as a whole-word error.
    text = text.replace("‑", "-").replace("-", " ")
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def tokens(text: str) -> list[str]:
    normalized = normalize_for_wer(text)
    return normalized.split() if normalized else []


def characters(text: str) -> list[str]:
    """Character sequence for CER: normalised, spaces collapsed but retained."""
    return list(normalize_for_wer(text))


def normalize_term(text: str) -> str:
    """Term-matching form: scoring normalisation plus Cyrillic-tail stripping.

    An earlier version also dropped a final Latin vowel from any token of five
    characters or more, to make `Kafka` match `Kafkу`. That was wrong in the
    most damaging way available: it folded `Kafka` and `Kafko` to the same
    stem, so a mangled product name scored as a correct one — under a primary
    metric whose entire purpose is catching mangled product names. The rule is
    removed. Inflection is handled by stripping the *Cyrillic* tail, which
    cannot merge two Latin spellings, and by listing genuine variants
    explicitly in `glossary.json` where a term needs them.
    """
    parts = []
    for token in tokens(text):
        if LATIN.search(token):
            # `Workerа` -> `worker`. Only a Cyrillic tail is stripped, so no
            # Latin character is ever discarded and no two distinct Latin
            # spellings can collapse into one.
            stripped = _RU_TAIL.sub("", token)
            if stripped and LATIN.search(stripped):
                token = stripped
        parts.append(token)
    return " ".join(parts)


def script_of(token: str) -> str:
    """`latin`, `cyrillic`, `mixed`, or `neutral` (digits, symbols)."""
    has_latin = bool(LATIN.search(token))
    has_cyrillic = bool(CYRILLIC.search(token))
    if has_latin and has_cyrillic:
        return "mixed"
    if has_latin:
        return "latin"
    if has_cyrillic:
        return "cyrillic"
    return "neutral"
