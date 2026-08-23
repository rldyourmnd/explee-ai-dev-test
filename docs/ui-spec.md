# Shared UI specification — the dashboard and the report

Both public pages are read by the same person in the same sitting, and today they
look like they came from different companies. This file makes them one thing and
fixes what I found by opening each at 1440 px.

Reference for what to avoid: [impeccable](https://github.com/pbakaus/impeccable),
which catalogues the tells of machine-generated interfaces. Its relevant
anti-patterns: overused fonts and system defaults, untinted greys, pure black,
cards wrapped in cards, purple gradients, dark glows, bounce easing, cramped
padding, over-long measure, skipped heading levels.

## Fix this first: the report's results table is broken

It is the central artifact of Task 2 and it does not read. At 1440 px the headers
wrap to three lines (`GPU S / HOUR`, `CODE- SWITCH WER`, `95 % INTERVAL`), the
numeric columns do not align, and an orphaned `←` sits on its own line under
*Whisper large-v3*. Everything else on this page is good writing wasted behind an
unreadable table.

- Give the table `table-layout: fixed` and explicit column widths. The engine
  column takes the slack; numeric columns are sized to their content.
- Move units into the header, once: `GPU s/h`, not a header that wraps around a
  slash. Shorten headers to fit one line: `Term F1`, `95% CI`, `Recall`,
  `Precision`, `WER`, `CS-WER`, `Lat→Cyr`, `GPU s/h`.
- All numbers right-aligned, `font-variant-numeric: tabular-nums`, identical
  decimal places down each column. A reader compares columns vertically; ragged
  decimals make that impossible.
- The confidence interval is one unbreakable unit: `0.406–0.622` with a
  non-breaking hyphen, never wrapped across lines.
- Mark the recommended row with a background tint and a label in the engine cell,
  not a floating arrow. `Whisper large-v3 · recommended`.
- Wrap the table in `overflow-x: auto` so the page body never scrolls sideways at
  narrow widths.

## The shared palette

The report's warm paper base wins; the dashboard adopts it. Reasons: `#0d1117` is
recognisably GitHub and reads as a template; a light surface scans better in
daylight, which is when someone checks spend; and the report's accents already
carry meaning rather than decoration.

```css
:root {
  --paper:   #fbfbfa;   /* page ground, warm off-white, never pure #fff */
  --surface: #f4f3f0;   /* table headers, code, inset panels */
  --rule:    #e4e3df;   /* hairlines */
  --ink:     #1c1d1f;   /* body text, tinted, never #000 */
  --muted:   #5f6570;   /* secondary text, tinted grey, never #888 */
  --alarm:   #8a3324;   /* critical: act now */
  --warn:    #8a6d3a;   /* warning: watch */
  --ok:      #2f6b47;   /* healthy */
  --accent:  #2f4f6b;   /* links and non-status emphasis */
}
```

Every colour is tinted; nothing sits on the neutral axis. Status colours mean
exactly one thing on both pages: brick red means a human must act. Never use a
status colour for decoration, and never use `--accent` for status.

## Type

```css
--sans: "Söhne", "Suisse Int'l", "Helvetica Neue", Helvetica, sans-serif;
--serif: "Tiempos Text", Charter, Georgia, serif;   /* report prose */
--mono: ui-monospace, "SF Mono", Menlo, monospace;  /* all figures */
```

The dashboard sets **no** `font-family` today, handing the page to the browser
default. That is impeccable's first anti-pattern. Set the stack explicitly.

Scale, and nothing between these steps: `12 / 13 / 15 / 17 / 21 / 28 / 38`.
Line-height `1.5` for prose, `1.25` for headings, `1.4` for dense table rows.
Measure capped at `68ch`; the report's paragraphs currently run wider on a large
screen. Headings descend without skipping a level.

Every figure a reader compares goes in `--mono` with `tabular-nums`. This applies
to the dashboard's value, burn and freshness columns as much as to the report's
table.

## Spacing

One scale: `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64`. No one-off values. Section
gaps at 48, panel padding at 24, table cell padding at `12 16`. Both pages are
currently tighter than they need to be, which impeccable names as cramped
padding.

Cards never nest. If a group needs a boundary, use a hairline and a heading, not
a second box inside the first.

## Dashboard specifics

**The five summary cards are wrong as peers.** `credits_package · credits`,
`postpaid · usd`, `prepaid_balance · gbp`, `prepaid_balance · usd` and
`spend_report · usd` currently look equally important, and a reader cannot tell
in one glance which one needs them. Rank them by urgency, lead with the one
closest to impact, and let the rest be smaller. The point of the page is the
first sentence a reader forms, and right now that sentence is "there are five
boxes".

**Every sparkline is the same red**, including providers burning down entirely
normally. Colour must carry meaning: `--muted` for a normal downward slope,
`--warn` when the projection crosses the warning horizon, `--alarm` when it
crosses critical, `--ok` for a top-up step. Right now the line says "everything
is bad", which is the same as saying nothing.

**Secondary metadata is too quiet.** `n=639, 327 min` under each burn figure is
small, low contrast and unlabelled. Either give it enough contrast to be read or
move it behind a hover title. Text nobody can read is noise that costs space.

Keep: the top status line, the risk ordering, the freshness badges, and the
`not summed — one vendor's credit is not another's` note, which is the most
honest thing on the page. Rewrite it without the dash.

## Prose

**No em dashes.** 34 on the report, 21 on the dashboard. They are the strongest
tell in machine-written text. Each becomes a comma, a colon, a full stop or
parentheses; if a sentence only worked with the dash, rewrite the sentence.

Fix the spaced percent sign: `63 % of technical terms` should be `63%`. Same for
`95 %`. Pick one convention and hold it everywhere.

Avoid the generated-text vocabulary: delve, leverage, robust, seamless,
comprehensive, crucial, pivotal, testament, landscape, realm, showcase,
underscore, elevate, unlock, tapestry, moreover, furthermore. Judge by meaning:
`SeamlessM4T` is a model name and stays; `harness` in "evaluation harness" is the
right technical word and stays.

No exclamation marks. No rhetorical question as a heading — the report's current
`Which transcriber actually hears our speech?` is the one exception worth
keeping, because it is the actual question the employer asked.

## Verification before calling it done

```bash
for u in https://spend.nddev.it.com/ https://stt.nddev.it.com/; do
  printf '%s em-dashes: ' "$u"
  curl -s "$u" | python3 -c "import sys;print(sys.stdin.read().count(chr(8212)))"
done
```

Expect zero on each. Then open both at 1440 px and 390 px: neither may scroll
horizontally, no table header may wrap to more than one line, and no number may
sit ragged against its column. Confirm a status colour means the same thing on
both pages.
