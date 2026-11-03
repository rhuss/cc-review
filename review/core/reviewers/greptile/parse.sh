#!/bin/sh
# Converts `greptile review --json` output (stdin, one JSON object) into a
# cc-review `json` finding array (stdout). Exits non-zero (a parse error for
# the review core) when stdin is empty, holds more than one value, or is not a
# review object with a `comments` array, so a failed run is never read as a
# clean one.
exec jq -s '
  if length != 1 or (.[0] | type) != "object" or (.[0].comments | type) != "array" then
    "greptile output is not a single review object with a comments array\n" | halt_error(1)
  else .[0].comments end
  | map(
      (.body // "") as $body
      | ([$body | split("\n")[] | select(test("\\S"))] | .[0] // "") as $first
      # Comments on removed lines (side "old") carry old-file line numbers;
      # anchor them at the start of the hunk in the new file instead.
      | (if .side == "old" then (.hunk.newRange.start // 1) else (.startLine // 1) end) as $line
      | (if .side == "old" then $line else (.endLine // .startLine // $line) end) as $line_end
      | {
          file: .path,
          line: $line,
          line_end: $line_end,
          severity: .severity,
          description: ($first | gsub("^\\s*\\*\\*|\\*\\*\\s*$"; "")),
          rationale: $body,
          confidence: 75
        }
      + (if (.suggestion | type) == "string" and .suggestion != "" then {fix: .suggestion} else {} end)
    )
'
