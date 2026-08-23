# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Extract the publisher's human transcript from the Habr article.

This is the reference, and it is what makes the benchmark scoreable: it was
written by people, published by the conference, and is independent of every
engine being ranked. Nothing here invents or corrects text — it strips HTML and
drops the furniture around the transcript (slide captions, the article's own
headings, code blocks), recording how much was dropped so the reader can see
the extraction was not a rewrite.

Stdlib only.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Habr wraps the article body in this container.
BODY = re.compile(
    r'<div[^>]+class="[^"]*article-formatted-body[^"]*"[^>]*>(.*?)</div>\s*</div>',
    re.DOTALL,
)
# Slide images carry captions that were never spoken.
FIGURE = re.compile(r"<figure.*?</figure>", re.DOTALL)
CODE = re.compile(r"<pre.*?</pre>|<code.*?</code>", re.DOTALL)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t ]+")


PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.DOTALL)


def extract(html_text: str) -> dict:
    """Pull the transcript paragraphs out of the article body.

    Matching the body container by its closing tag does not work — Habr nests
    divs inside it, so a non-greedy match stops at the first inner close and
    returns only the abstract. Instead we slice from the container marker to
    the end of the document and take every `<p>`, which is what the transcript
    is made of.
    """
    marker = html_text.find("article-formatted-body")
    if marker < 0:
        raise SystemExit("article body not found; the page structure changed")
    body = html_text[marker:]
    before = len(body)
    body = FIGURE.sub(" ", body)
    body = CODE.sub(" ", body)

    kept: list[str] = []
    dropped = 0
    for raw in PARAGRAPH.findall(body):
        raw = re.sub(r"<br\s*/?>", " ", raw)
        line = WS.sub(" ", html.unescape(TAG.sub(" ", raw))).strip()
        if not line:
            continue
        # Slide captions are short, image-only paragraphs; keeping them would
        # charge every engine for words nobody said.
        if len(line) < 3:
            dropped += 1
            continue
        kept.append(line)

    # The article opens with its own abstract ("Доклад посвящён…", a bullet list
    # of what the talk will cover). Nobody said those words aloud, so scoring
    # them would charge every engine for the editor's prose. The transcript
    # proper begins where the speaker introduces himself.
    anchor = next(
        (i for i, line in enumerate(kept) if line.startswith("Меня зовут")), None
    )
    abstract_dropped = anchor or 0
    if anchor is not None:
        kept = kept[anchor:]

    text = "\n".join(kept)
    return {
        "abstract_paragraphs_dropped": abstract_dropped,
        "text": text,
        "chars_before_stripping": before,
        "paragraphs": len(kept),
        "paragraphs_dropped_as_furniture": dropped,
        "words": len(text.split()),
    }


def main() -> int:
    source = Path(sys.argv[1])
    out = HERE / "data" / "reference-hlk8s.json"
    result = extract(source.read_text(encoding="utf-8", errors="replace"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "source_url": "https://habr.com/ru/articles/523378/",
                "talk": "Оператор в Kubernetes для управления кластерами БД",
                "speaker": "Владислав Клименко (Altinity)",
                "video_id": "z2aARjKDg4w",
                "kind": "publisher human transcript, edited for readability",
                **result,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"words={result['words']} paragraphs={result['paragraphs']}")
    print(result["text"][:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
