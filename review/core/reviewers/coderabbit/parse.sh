#!/bin/sh
# Converts `coderabbit review --agent` JSON-lines output (stdin) into a
# cc-review `json` finding array (stdout). Non-JSON lines and non-finding
# objects are ignored. Exits non-zero (a parse error for the review core) when
# the stream reports an error, asks for user action, or ends without its
# `complete` event, so a failed or truncated run is never read as a clean one.
exec jq -R -s '
  [ split("\n")[] | select(startswith("{")) | (fromjson? // empty) | select(type == "object") ] as $events
  | if any($events[]; .type == "error" or .type == "action_required") then
      ("coderabbit reported an error: "
        + ([$events[] | select(.type == "error" or .type == "action_required")
            | (.message // .error // .status // .type) | tostring][0]) + "\n") | halt_error(1)
    elif any($events[]; .type == "complete") | not then
      "coderabbit output ended without a complete event (truncated or failed run)\n" | halt_error(1)
    else . end
  | [ $events[] | select(.type == "finding") ]
  | map(
      ((.codegenInstructions // "") | split("\n") | map(select(length > 0))) as $lines
      | ([$lines | to_entries[] | select(.value | startswith("Review comment at @")) | .key] | .[0] // -1) as $hdr
      # The location is read from the header line only: the comment body may
      # mention other line numbers.
      | (if $hdr >= 0 then $lines[$hdr] else "" end) as $header
      | (($header | capture("around lines? (?<a>[0-9]+)(?: *- *(?<b>[0-9]+))?"))
          // ($header | capture("at line (?<a>[0-9]+)"))
          // {a: "1", b: null}) as $ln
      | ($lines[($hdr + 1):] | join("\n")) as $comment
      | {
          file: .fileName,
          line: ($ln.a | tonumber),
          line_end: (if $ln.b then ($ln.b | tonumber) else ($ln.a | tonumber) end),
          severity: .severity,
          description: (($comment | split("\n") | .[0]) // ""),
          rationale: $comment,
          confidence: 75
        })
'
