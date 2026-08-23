#!/usr/bin/env bash
# Send a message to a cmux pane and PROVE it was submitted.
#
# `cmux send` types text into the target prompt; it does not submit it. Sending
# Enter immediately afterwards races the paste - the text is still arriving when
# the keystroke lands, so the message sits at the prompt unsent and the sender
# has no idea. That has happened repeatedly here and the human has had to press
# Enter by hand. Delivery is a claim like any other: it is not done until the
# screen proves it.
#
# Usage: tools/cmux_send.sh <surface-ref> <message>
#    e.g. tools/cmux_send.sh surface:5 "your instruction here"
#
# Exits non-zero if the message could not be confirmed as submitted.

set -uo pipefail

SURFACE="${1:?usage: cmux_send.sh <surface-ref> <message>}"
MESSAGE="${2:?usage: cmux_send.sh <surface-ref> <message>}"
ATTEMPTS="${CMUX_SEND_ATTEMPTS:-4}"

# A pane is idle-with-unsent-text when the prompt line still carries content.
# "Press up to edit queued messages" means the recipient is busy and the message
# is queued - that is delivered, not stuck.
prompt_holds_text() {
  local screen
  screen="$(cmux read-screen --surface "$SURFACE" --lines 6 2>/dev/null)" || return 1
  grep -q "Press up to edit queued messages" <<<"$screen" && return 1
  grep -qE '^❯[[:space:]]+[^[:space:]]' <<<"$screen"
}

cmux send --surface "$SURFACE" "$MESSAGE" >/dev/null 2>&1 || {
  echo "FAIL $SURFACE: cmux send rejected the message" >&2
  exit 1
}

for attempt in $(seq 1 "$ATTEMPTS"); do
  sleep 1                                    # let the paste finish arriving
  cmux send-key --surface "$SURFACE" Enter >/dev/null 2>&1
  sleep 2                                    # let the TUI redraw
  if ! prompt_holds_text; then
    echo "OK $SURFACE: submitted (attempt $attempt)"
    exit 0
  fi
done

echo "FAIL $SURFACE: text still sitting at the prompt after $ATTEMPTS attempts - press Enter by hand" >&2
exit 1
