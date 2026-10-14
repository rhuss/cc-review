#!/usr/bin/env bash
#
# discover-reviewers.sh: three-layer reviewer plugin discovery for cc-review.
#
# Executed:
#   discover-reviewers.sh --core-dir <core> [--project-dir <git-root>] [--user-dir <dir>]
#                         [--pr <number>] [--spec <path>] [--changed-files <file>]
#                         [--trust-file <file>] [--body-dir <dir>]
#                         [--skip-detection] [--verbose]
#
#   Scans <core>/reviewers/, <user-dir> (default $HOME/.cc-review/reviewers) and
#   <project-dir>/.cc-review/reviewers/ for <name>.md and <name>/reviewer.md,
#   validates frontmatter, resolves overrides by name (project > user > bundled),
#   evaluates preconditions and prints one JSON array on stdout. Warnings go to
#   stderr prefixed "Warning:", verbose notes prefixed "Note:".
#
#   Project-layer reviewers come from the checkout under review, so two guards
#   apply to them. A reviewer whose files appear in --changed-files (one
#   repo-relative path per line) is ignored for the run and the next lower
#   layer's reviewer of the same name is used. A kind: command reviewer runs
#   nothing (no detect, auth_check, invoke or parser) unless --trust-file
#   (default $HOME/.cc-review/trusted-reviewers) lists "<name> <sha256>" for
#   its current files (the reviewer file, or every file in its directory).
#
#   Body files (frontmatter stripped) are written to --body-dir, an existing
#   empty directory the caller creates and removes. Without --body-dir, the
#   script creates a private directory with mktemp -d
#   (${TMPDIR:-/tmp}/cc-review-reviewers.XXXXXX) and removes it again when no
#   body file remains.
#
#   Each output element: name, kind, display_name, category, enabled, requires,
#   severity_map, dedup, references (absolute paths), context, command
#   ({detect, auth_check, invoke, timeout_seconds, output} or null), layer,
#   path, dir, body_file, overrides (layer replaced, or null), status
#   (ready | skipped | invalid) and reason (null when ready). The full status
#   set, including the values the review command adds, is documented in
#   specs/004-reviewer-plugins/contracts/discovery-output.md.
#
#   The runtime helpers (enablement, selection, detection, timeouts) live in
#   reviewer-runtime.sh next to this script.

CC_REVIEW_DISCOVER_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=reviewer-runtime.sh
. "$CC_REVIEW_DISCOVER_DIR/reviewer-runtime.sh"

# Frontmatter contract, defined once here; reviewer.schema.json must agree with
# these values (tests/run.sh compares them).
CC_REVIEW_RESERVED_NAMES="external fix meta-review only sequential parallel pr spec hints output config profile max-rounds"
CC_REVIEW_NAME_PATTERN='^[a-z0-9][a-z0-9-]*$'
CC_REVIEW_CATEGORY_PATTERN='^[a-z0-9-]+$'
CC_REVIEW_KINDS="prompt command"
CC_REVIEW_DEDUP_MODES="cross-category isolated"
CC_REVIEW_CONTEXT_BLOCKS="goals"
CC_REVIEW_OUTPUT_FORMATS="json delimited parser"
CC_REVIEW_DELIMITED_FIELDS="file line severity description"
CC_REVIEW_PLACEHOLDERS="base_branch files pr_number"
CC_REVIEW_DEFAULT_TIMEOUT=120

CC_REVIEW_DISCOVER_VERBOSE="${CC_REVIEW_DISCOVER_VERBOSE:-false}"

# Named fields of the two intermediate formats. The jq validator emits the
# validation fields in this order and the shell reads them back by name; the
# shell writes the row fields in this order and the final jq call reads them
# by name. Adding a field means adding it here and where it is produced.
CC_REVIEW_VALIDATE_FIELDS="error kind refs parser unknown requires invoke detect auth_check"
CC_REVIEW_ROW_FIELDS="layer name kind path dir body_file status reason refs parser_path"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_discover_warn() {
  printf 'Warning: %s\n' "$*" >&2
}

_discover_note() {
  [ "$CC_REVIEW_DISCOVER_VERBOSE" = "true" ] && printf 'Note: %s\n' "$*" >&2
  return 0
}

# ---------------------------------------------------------------------------
# Discovery internals
# ---------------------------------------------------------------------------

_discover_usage() {
  cat >&2 <<'EOF'
Usage: discover-reviewers.sh --core-dir <path> [--project-dir <path>] [--user-dir <path>]
                             [--pr <number>] [--spec <path>] [--changed-files <file>]
                             [--trust-file <file>] [--body-dir <dir>]
                             [--skip-detection] [--verbose]
EOF
}

# _discover_check_relative <plugin_dir> <relative_path>
# Returns 0 and prints the absolute path when the path is relative, has no ".."
# segment, is not a symlink, and physically resolves to a regular file inside
# the plugin directory (a symlinked parent directory pointing elsewhere is
# rejected too).
_discover_check_relative() {
  local dir="$1" rel="$2" base real
  case "$rel" in
    /*) return 1 ;;
    ..|../*|*/..|*/../*) return 1 ;;
    "") return 1 ;;
  esac
  [ -f "$dir/$rel" ] && [ ! -L "$dir/$rel" ] || return 1
  base="$(cd -P "$dir" 2>/dev/null && pwd -P)" || return 1
  # Parent via parameter expansion: dirname(1) would treat a leading "-" as an
  # option and silently return nothing, defeating the containment check.
  local parent
  case "$rel" in
    */*) parent="${rel%/*}" ;;
    *) parent="." ;;
  esac
  real="$(cd -P "$dir/$parent" 2>/dev/null && pwd -P)" || return 1
  case "$real/" in
    "$base"/*) ;;
    *) return 1 ;;
  esac
  printf '%s/%s' "$dir" "$rel"
}

# _discover_sha256 <file>: prints the lowercase hex SHA-256 of the file.
_discover_sha256() {
  local sum _rest
  case "$CC_REVIEW_SHA256_TOOL" in
    sha256sum) read -r sum _rest < <(sha256sum < "$1") ;;
    shasum) read -r sum _rest < <(shasum -a 256 < "$1") ;;
    openssl) sum="$(openssl dgst -sha256 -r < "$1")"; sum="${sum%% *}" ;;
    *) return 1 ;;
  esac
  [ -n "$sum" ] || return 1
  printf '%s' "$sum" | tr 'A-F' 'a-f'
}

# _discover_trust_digest <reviewer_file> [<parser_file>]
# The digest a trust entry pins: the SHA-256 of the hex digests of the reviewer
# file and, when declared, the parser script, one per line. Editing either
# file changes it.
_discover_trust_digest() {
  local list="$CC_REVIEW_BODY_DIR/.trust-digest" f h rc=0
  : > "$list"
  for f in "$@"; do
    [ -n "$f" ] || continue
    h="$(_discover_sha256 "$f")" || { rc=1; break; }
    printf '%s\n' "$h" >> "$list"
  done
  [ "$rc" -eq 0 ] && { _discover_sha256 "$list" || rc=1; }
  rm -f "$list"
  return $rc
}

# _discover_trust_digest_dir <plugin_dir>
# Directory-form digest: the SHA-256 over "<hex digest> <relative path>" for
# every regular file in the plugin directory, sorted by path. A parser that
# sources a helper next to it is therefore pinned too. Returns 2 when the
# directory holds a symlink or a file name with a newline (cannot be pinned),
# 1 when no SHA-256 tool works.
_discover_trust_digest_dir() {
  local pdir="$1" list="$CC_REVIEW_BODY_DIR/.trust-digest" f h rc=0
  if [ -n "$(find "$pdir" -type l -print 2>/dev/null | head -n 1)" ] \
    || [ -n "$(find "$pdir" -name "$(printf '*\n*')" -print 2>/dev/null | head -n 1)" ]; then
    return 2
  fi
  : > "$list"
  while IFS= read -r f; do
    h="$(_discover_sha256 "$f")" || { rc=1; break; }
    printf '%s %s\n' "$h" "${f#"$pdir"/}" >> "$list"
  done < <(find "$pdir" -type f -print | LC_ALL=C sort)
  [ "$rc" -eq 0 ] && { _discover_sha256 "$list" || rc=1; }
  rm -f "$list"
  return $rc
}

# _discover_is_changed <reviewer_file> <plugin_dir> <layer_dir> <refs (0x1e)> <parser_path>
# Returns 0 when a file of this project-layer reviewer is in the changed-file
# list: the reviewer file, any file below a directory-form plugin, a reference
# or the parser.
_discover_is_changed() {
  local path="$1" pdir="$2" layer_dir="$3" refs="$4" parser_path="$5" rel ref
  local root="$CC_REVIEW_PROJECT_ROOT/"
  local -a candidates=("$path")
  if [ -n "$refs" ]; then
    local -a ref_list=()
    IFS=$'\x1e' read -r -a ref_list <<< "$refs"
    for ref in "${ref_list[@]}"; do candidates+=("$ref"); done
  fi
  [ -n "$parser_path" ] && candidates+=("$parser_path")
  for ref in "${candidates[@]}"; do
    [ -n "$ref" ] || continue
    rel="${ref#"$root"}"
    case "$CC_REVIEW_DISCOVER_CHANGED" in
      *$'\n'"$rel"$'\n'*) return 0 ;;
    esac
  done
  if [ "$pdir" != "$layer_dir" ]; then
    rel="${pdir#"$root"}/"
    case "$CC_REVIEW_DISCOVER_CHANGED" in
      *$'\n'"$rel"*) return 0 ;;
    esac
  fi
  return 1
}

# jq program: validates one frontmatter object against the contract and emits the
# normalized record, or {"error": "<reason>"}. Input: {i, fm}; $keys[i] is the
# expected name and $empties[i] the body-empty flag ("true"/"false").
# Output per element: the record as JSON on one line, then the fields named in
# $validate_fields on a second line, in that order, separated by the ASCII unit
# separator (0x1f); lists inside a field are separated by the record separator
# (0x1e) and newlines travel as vertical tabs (0x0b).
# shellcheck disable=SC2016
CC_REVIEW_VALIDATE_JQ='
  def validate($expected; $body_empty):
    def err(m): {error: m};
    ["name","kind","display_name","category","enabled","requires","severity_map","dedup",
       "references","context","detect","auth_check","invoke","timeout_seconds","output"] as $known
    # An empty display_name means "use the name".
    | (if type == "object" and has("display_name") and .display_name == "" then del(.display_name) else . end)
    | . as $fm
    | def bad_sev: ($fm.severity_map | to_entries | map(select((.value | type) != "string" or (.value as $v | $sev_list | index($v)) == null)));
      # YAML reads 007, 1e3, 0x1f or true as a number or boolean, whose text
      # cannot be recovered after parsing; the author must quote such values.
      def unquoted: type == "number" or type == "boolean";
      def bad_placeholders: [.invoke | gsub("\\$\\{[^}]*\\}"; "") | scan("\\{[A-Za-z_][A-Za-z0-9_]*\\}")
        | select((ltrimstr("{") | rtrimstr("}")) as $p | ($placeholder_list | index($p)) == null)];
      if type != "object" then err("frontmatter missing or malformed")
      elif (.name | unquoted) then err("name must be a quoted string")
      elif (.name | type) != "string" or (.name | test($name_pattern) | not) then err("invalid name")
      elif .name != $expected then err("name does not match file or directory name")
      elif ($reserved_list | index($fm.name)) != null then err("reserved name")
      elif (.kind | type) != "string" or ($kind_list | index($fm.kind)) == null then err("unknown kind")
      elif has("display_name") and (.display_name | type) != "string" then err("invalid display_name")
      elif has("category") and (.category | unquoted) then err("category must be a quoted string")
      elif has("category") and ((.category | type) != "string" or (.category | test($category_pattern) | not)) then err("invalid category")
      elif has("enabled") and (.enabled | type) != "boolean" then err("invalid enabled value")
      elif has("requires") and ((.requires | type) != "array" or (.requires | all(type == "string") | not)) then err("invalid requires list")
      elif has("severity_map") and (.severity_map | type) != "object" then err("invalid severity_map")
      elif has("severity_map") and (bad_sev | length) > 0
        then err("invalid severity_map value: " + (bad_sev | .[0].value | tostring))
      elif has("dedup") and ((.dedup | type) != "string" or ($dedup_list | index($fm.dedup)) == null) then err("unknown dedup mode")
      elif .kind == "prompt" and $body_empty == "true" then err("empty prompt body")
      elif .kind == "prompt" and has("references") and ((.references | type) != "array" or (.references | all(type == "string") | not)) then err("invalid references list")
      elif .kind == "prompt" and has("context") and ((.context | type) != "array" or (.context | all(type == "string") | not)) then err("invalid context list")
      elif .kind == "prompt" and has("context") and (.context | map(select(. as $c | ($context_list | index($c)) == null)) | length) > 0
        then err("unknown context block: " + (.context | map(select(. as $c | ($context_list | index($c)) == null)) | .[0]))
      elif .kind == "command" and ((.detect | type) != "string" or .detect == "") then err("command reviewer missing detect")
      elif .kind == "command" and ((.invoke | type) != "string" or .invoke == "") then err("command reviewer missing invoke")
      elif .kind == "command" and ((.output | type) != "object" or (.output.format | type) != "string") then err("command reviewer missing output.format")
      elif .kind == "command" and has("auth_check") and (.auth_check | type) != "string" then err("invalid auth_check")
      elif .kind == "command" and (bad_placeholders | length) > 0 then err("unknown placeholder " + (bad_placeholders | .[0]))
      elif .kind == "command" and ($format_list | index($fm.output.format)) == null then err("incomplete output declaration")
      elif .kind == "command" and .output.format == "delimited" and (
             (.output.delimiter | type) != "string" or .output.delimiter == ""
             or (.output.fields | type) != "object"
             or ($delimited_fields | all(. as $f | $fm.output.fields | has($f)) | not)
             or (.output.fields | to_entries | all(.value | type == "string") | not)) then err("incomplete output declaration")
      elif .kind == "command" and .output.format == "parser" and ((.output.parser | type) != "string" or .output.parser == "") then err("incomplete output declaration")
      elif .kind == "command" and has("timeout_seconds") and ((.timeout_seconds | type) != "number" or .timeout_seconds < 1 or (.timeout_seconds | floor) != .timeout_seconds) then err("invalid timeout_seconds")
      else {
        name: .name,
        kind: .kind,
        display_name: (.display_name // .name),
        category: (.category // .name),
        enabled: (if has("enabled") then .enabled else true end),
        requires: (.requires // []),
        severity_map: (.severity_map // {}),
        dedup: (.dedup // "cross-category"),
        references_raw: (if .kind == "prompt" then (.references // []) else [] end),
        context: (if .kind == "prompt" then (.context // []) else [] end),
        command: (if .kind == "command" then {
            detect: .detect,
            auth_check: (.auth_check // null),
            invoke: .invoke,
            timeout_seconds: (.timeout_seconds // $default_timeout),
            output: .output
          } else null end),
        unknown_fields: [keys[] | select(. as $k | ($known | index($k)) == null)]
      } end
  ;
  .[]
  | . as $el
  | ($el.fm | validate($keys[$el.i]; $empties[$el.i]))
  | tojson,
    ({error: (.error // ""),
      kind: (.kind // (($el.fm | if type == "object" and (.kind | type) == "string" then .kind else "" end))),
      refs: ((.references_raw // []) | join("\u001e")),
      parser: (.command.output.parser // ""),
      unknown: ((.unknown_fields // []) | join(", ")),
      requires: ((.requires // []) | join("\u001e")),
      invoke: (.command.invoke // ""),
      detect: (.command.detect // ""),
      auth_check: (.command.auth_check // "")} as $v
     | [$validate_fields[] | . as $k | if ($v | has($k)) then $v[$k] else error("validator does not produce field " + $k) end]
     | join("\u001f") | gsub("\n"; "\u000b"))
'

# _discover_record [record_json]
# Appends one result row and one record line to the global accumulators. The
# row is built from the variables _dr_<field> for every field in
# CC_REVIEW_ROW_FIELDS (callers set them as prefix assignments, so unset
# fields are empty); newlines inside a value travel as vertical tabs.
_discover_record() {
  local f v line=""
  for f in $CC_REVIEW_ROW_FIELDS; do
    v="_dr_$f"
    v="${!v:-}"
    line="$line${v//$'\n'/$'\v'}"$'\x1f'
  done
  printf '%s\n' "$line" >> "$CC_REVIEW_DISCOVER_ROWS"
  printf '%s\n' "${1:-null}" >> "$CC_REVIEW_DISCOVER_RECORDS"
}

# _discover_scan_layer <layer_dir> <layer_name>
_discover_scan_layer() {
  local dir="$1" layer="$2"
  [ -d "$dir" ] || return 0
  # CDPATH would make cd print the directory and change the captured value.
  dir="$(CDPATH='' cd -- "$dir" && pwd)" || return 0

  # 1. Enumerate reviewer files: file form first, then directory form (file wins on a clash)
  local -a keys=() paths=() dirs=()
  # The intermediate files below are framed by newlines, tabs and the ASCII
  # separators 0x1e/0x1f, so names holding any control character are rejected
  # up front (FR-005 excludes them anyway).
  local entry base name
  for entry in "$dir"/*.md; do
    [ -f "$entry" ] || continue
    base="${entry##*/}"
    case "$base" in
      *[[:cntrl:]]*) _discover_warn "skipping reviewer $(printf '%q' "$entry"): unsupported characters in file name"; continue ;;
    esac
    keys+=("${base%.md}"); paths+=("$entry"); dirs+=("$dir")
  done
  for entry in "$dir"/*/; do
    [ -d "$entry" ] || continue
    entry="${entry%/}"
    name="${entry##*/}"
    [ -f "$entry/reviewer.md" ] || continue
    case "$name" in
      *[[:cntrl:]]*) _discover_warn "skipping reviewer $(printf '%q' "$entry")/reviewer.md: unsupported characters in directory name"; continue ;;
    esac
    if [ -f "$dir/$name.md" ]; then
      _discover_warn "both $dir/$name.md and $entry/reviewer.md exist in the $layer layer; using the file form"
      continue
    fi
    keys+=("$name"); paths+=("$entry/reviewer.md"); dirs+=("$entry")
  done
  [ ${#keys[@]} -gt 0 ] || return 0

  # 2. One awk pass: split frontmatter and body for every file, build one YAML stream
  local list="$CC_REVIEW_BODY_DIR/.$layer.list" stream="$CC_REVIEW_BODY_DIR/.$layer.stream.yml"
  local i
  : > "$list"
  for i in "${!keys[@]}"; do
    printf '%s\t%s\n' "${keys[$i]}" "${paths[$i]}" >> "$list"
  done
  : > "$stream"
  local -a states=()
  local line
  while IFS= read -r line; do
    states+=("$line")
  done < <(awk -F '\t' -v outdir="$CC_REVIEW_BODY_DIR" -v layer="$layer" -v stream="$stream" '
    {
      key = $1; path = $2
      body = outdir "/" layer "-" key ".md"
      fm = outdir "/" layer "-" key ".fm.yml"
      printf "" > body; printf "" > fm
      infm = 0; done = 0; nonblank = 0; first = 1; state = "nofm"; fmlines = 0
      while ((getline l < path) > 0) {
        sub(/\r$/, "", l)
        if (first) {
          first = 0
          if (l ~ /^---[[:space:]]*$/) { infm = 1; continue } else { break }
        }
        if (infm && l ~ /^---[[:space:]]*$/) { infm = 0; done = 1; continue }
        if (infm) { print l > fm; fmlines++; continue }
        if (done) { print l > body; if (l ~ /[^[:space:]]/) nonblank = 1 }
      }
      close(path); close(body); close(fm)
      if (done) {
        state = nonblank ? "ok:body" : "ok:empty"
        printf "- i: %d\n", n > stream
        if (fmlines == 0) { print "  fm: null" > stream }
        else {
          print "  fm:" > stream
          while ((getline l < fm) > 0) { sub(/\r$/, "", l); print "      " l > stream }
          close(fm)
        }
        n++
      } else if (infm) state = "unclosed"
      print state
    }
  ' "$list")

  # 3. One yq call for the whole layer; fall back to per-file parsing when the
  #    combined stream is malformed so one bad file does not hide the others.
  local -a ok_idx=()
  local fm_json="[]"
  for i in "${!keys[@]}"; do
    case "${states[$i]}" in ok:*) ok_idx+=("$i") ;; esac
  done
  if [ ${#ok_idx[@]} -gt 0 ]; then
    if ! fm_json="$(yq -o=json -I=0 '.' "$stream" 2>/dev/null)" || [ -z "$fm_json" ] || [ "$fm_json" = "null" ]; then
      fm_json=""
      local n=0 one
      for i in "${ok_idx[@]}"; do
        if one="$(yq -o=json -I=0 '.' "$CC_REVIEW_BODY_DIR/${layer}-${keys[$i]}.fm.yml" 2>/dev/null)" && [ -n "$one" ]; then
          fm_json="${fm_json:+$fm_json,}{\"i\":$n,\"fm\":$one}"
        else
          fm_json="${fm_json:+$fm_json,}{\"i\":$n,\"fm\":\"malformed\"}"
        fi
        n=$((n + 1))
      done
      fm_json="[$fm_json]"
    fi
  fi

  # 4. One jq call validates every parsed frontmatter. The key and body-empty
  #    arrays are built by jq itself so a basename containing a quote or a
  #    backslash cannot break the JSON for the whole layer.
  local -a validated=() keys_ok=() empties_ok=()
  local keys_json="[]" empties_json="[]"
  if [ ${#ok_idx[@]} -gt 0 ]; then
    for i in "${ok_idx[@]}"; do
      keys_ok+=("${keys[$i]}")
      if [ "${states[$i]}" = "ok:empty" ]; then empties_ok+=("true"); else empties_ok+=("false"); fi
    done
    keys_json="$(jq -cn '$ARGS.positional' --args -- "${keys_ok[@]}")"
    empties_json="$(jq -cn '$ARGS.positional' --args -- "${empties_ok[@]}")"
    while IFS= read -r line; do
      validated+=("$line")
    done < <(printf '%s' "$fm_json" | jq -r \
      --argjson keys "$keys_json" --argjson empties "$empties_json" \
      --arg reserved "$CC_REVIEW_RESERVED_NAMES" --arg sevs "$CC_REVIEW_SEVERITIES" \
      --arg kinds "$CC_REVIEW_KINDS" --arg dedups "$CC_REVIEW_DEDUP_MODES" \
      --arg contexts "$CC_REVIEW_CONTEXT_BLOCKS" --arg formats "$CC_REVIEW_OUTPUT_FORMATS" \
      --arg dfields "$CC_REVIEW_DELIMITED_FIELDS" --arg placeholders "$CC_REVIEW_PLACEHOLDERS" \
      --arg vfields "$CC_REVIEW_VALIDATE_FIELDS" \
      --arg name_pattern "$CC_REVIEW_NAME_PATTERN" --arg category_pattern "$CC_REVIEW_CATEGORY_PATTERN" \
      --argjson default_timeout "$CC_REVIEW_DEFAULT_TIMEOUT" \
      '($reserved | split(" ")) as $reserved_list | ($sevs | split(" ")) as $sev_list
       | ($kinds | split(" ")) as $kind_list | ($dedups | split(" ")) as $dedup_list
       | ($contexts | split(" ")) as $context_list | ($formats | split(" ")) as $format_list
       | ($dfields | split(" ")) as $delimited_fields | ($placeholders | split(" ")) as $placeholder_list
       | ($vfields | split(" ")) as $validate_fields | '"$CC_REVIEW_VALIDATE_JQ")
  fi

  # 5. Filesystem checks, project-layer guards and preconditions per reviewer
  local n=0 key path pdir body_file record fields f j
  local -a F
  for i in "${!keys[@]}"; do
    key="${keys[$i]}"; path="${paths[$i]}"; pdir="${dirs[$i]}"
    body_file="$CC_REVIEW_BODY_DIR/${layer}-${key}.md"
    case "${states[$i]}" in
      ok:*) ;;
      *)
        rm -f "$body_file"
        _dr_layer="$layer" _dr_name="$key" _dr_path="$path" _dr_dir="$pdir" _dr_status="invalid" \
          _dr_reason="frontmatter missing or malformed" _discover_record
        continue
        ;;
    esac
    record="${validated[$((n * 2))]:-}"
    fields="${validated[$((n * 2 + 1))]:-}"
    n=$((n + 1))
    # Read the validation fields back by name into _dv_<field>, restoring the
    # newlines that travelled as vertical tabs (0x0b).
    F=()
    IFS=$'\x1f' read -r -a F <<< "$fields"
    j=0
    for f in $CC_REVIEW_VALIDATE_FIELDS; do
      printf -v "_dv_$f" '%s' "${F[$j]:-}"
      j=$((j + 1))
    done
    _dv_invoke="${_dv_invoke//$'\v'/$'\n'}"; _dv_detect="${_dv_detect//$'\v'/$'\n'}"
    _dv_auth_check="${_dv_auth_check//$'\v'/$'\n'}"
    _dv_refs="${_dv_refs//$'\v'/$'\n'}"; _dv_parser="${_dv_parser//$'\v'/$'\n'}"

    if [ -z "$record" ] || [ -n "$_dv_error" ]; then
      rm -f "$body_file"
      _dr_layer="$layer" _dr_name="$key" _dr_kind="$_dv_kind" _dr_path="$path" _dr_dir="$pdir" \
        _dr_status="invalid" _dr_reason="${_dv_error:-frontmatter missing or malformed}" _discover_record
      continue
    fi

    # References (prompt) and parser (command) must resolve inside the plugin directory
    local refs_abs="" parser_path="" ref resolved invalid_reason=""
    if [ "$_dv_kind" = "prompt" ] && [ -n "$_dv_refs" ]; then
      local -a raw_list=()
      IFS=$'\x1e' read -r -a raw_list <<< "$_dv_refs"
      for ref in "${raw_list[@]}"; do
        [ -z "$ref" ] && continue
        if resolved="$(_discover_check_relative "$pdir" "$ref")"; then
          refs_abs="${refs_abs:+$refs_abs$'\x1e'}$resolved"
        else
          invalid_reason="reference not found or outside plugin directory: $ref"
          break
        fi
      done
    elif [ "$_dv_kind" = "command" ] && [ -n "$_dv_parser" ]; then
      if ! parser_path="$(_discover_check_relative "$pdir" "$_dv_parser")" || [ ! -x "$parser_path" ]; then
        invalid_reason="parser not found or not executable"
      fi
    fi
    if [ -n "$invalid_reason" ]; then
      rm -f "$body_file"
      _dr_layer="$layer" _dr_name="$key" _dr_kind="$_dv_kind" _dr_path="$path" _dr_dir="$pdir" \
        _dr_status="invalid" _dr_reason="$invalid_reason" _discover_record
      continue
    fi

    [ -n "$_dv_unknown" ] && _discover_note "$path: ignoring unknown field(s): $_dv_unknown"

    local status="ready" reason="" token digest
    # Project-layer guards: the checkout under review supplies these files.
    # "changed" is an internal status resolved by the final jq call.
    if [ "$layer" = "project" ]; then
      if [ -n "$CC_REVIEW_DISCOVER_CHANGED" ] && _discover_is_changed "$path" "$pdir" "$dir" "$refs_abs" "$parser_path"; then
        status="changed"; reason="changed in the reviewed change"
      elif [ "$_dv_kind" = "command" ]; then
        local _dg_rc=0
        if [ "$pdir" != "$dir" ]; then
          digest="$(_discover_trust_digest_dir "$pdir")" || _dg_rc=$?
        else
          digest="$(_discover_trust_digest "$path" "$parser_path")" || _dg_rc=$?
        fi
        if [ "$_dg_rc" -eq 2 ]; then
          status="skipped"; reason="untrusted project command reviewer (its directory contains a symlink or a file name with a newline, which cannot be pinned)"
        elif [ "$_dg_rc" -ne 0 ]; then
          status="skipped"; reason="untrusted project command reviewer (no sha256 tool found)"
        else
          case "$CC_REVIEW_DISCOVER_TRUST" in
            *$'\n'"$key $digest"$'\n'*) ;;
            *) status="skipped"; reason="untrusted project command reviewer (trust with: $key $digest)" ;;
          esac
        fi
      fi
    fi

    # Preconditions
    if [ "$status" = "ready" ] && [ -n "$_dv_requires" ]; then
      local -a req_list=()
      IFS=$'\x1e' read -r -a req_list <<< "$_dv_requires"
      for token in "${req_list[@]}"; do
        [ -z "$token" ] && continue
        case "$token" in
          pr) [ -n "$CC_REVIEW_DISCOVER_PR" ] || { status="skipped"; reason="requires: pr"; } ;;
          spec) [ -n "$CC_REVIEW_DISCOVER_SPEC" ] || { status="skipped"; reason="requires: spec"; } ;;
          binary:*) command -v "${token#binary:}" >/dev/null 2>&1 || { status="skipped"; reason="requires: $token"; } ;;
          *) status="skipped"; reason="unknown precondition: $token" ;;
        esac
        [ "$status" = "skipped" ] && break
      done
    fi
    if [ "$status" = "ready" ] && [ "$_dv_kind" = "command" ]; then
      case "$_dv_invoke" in
        *"{pr_number}"*) [ -n "$CC_REVIEW_DISCOVER_PR" ] || { status="skipped"; reason="requires: pr"; } ;;
      esac
      if [ "$status" = "ready" ] && [ "$CC_REVIEW_DISCOVER_SKIP_DETECTION" != "true" ]; then
        # Both checks are plugin-supplied shell commands; _runtime_detect bounds
        # them so a hanging network call cannot stall discovery.
        reason="$(_runtime_detect "$_dv_detect" "$_dv_auth_check")"
        [ -n "$reason" ] && status="skipped"
      fi
    fi

    _dr_layer="$layer" _dr_name="$key" _dr_kind="$_dv_kind" _dr_path="$path" _dr_dir="$pdir" \
      _dr_body_file="$body_file" _dr_status="$status" _dr_reason="$reason" _dr_refs="$refs_abs" \
      _dr_parser_path="$parser_path" _discover_record "$record"
  done

  rm -f "$list" "$stream" "$CC_REVIEW_BODY_DIR"/"$layer"-*.fm.yml
}

# _discover_load_lines <file>: prints the file's non-empty lines framed by
# newlines ("\n<line>\n<line>\n"), for membership tests with case.
_discover_load_lines() {
  local out=$'\n' l
  while IFS= read -r l || [ -n "$l" ]; do
    l="${l%$'\r'}"
    [ -n "$l" ] && out="$out$l"$'\n'
  done < "$1"
  printf '%s' "$out"
}

# _discover_load_trust <file> <project_dir>
# Prints the "<name> <sha256>" entries of the trust file framed by newlines.
# Comments (#) and blank lines are skipped. A trust file inside the project
# under review is ignored with a warning: the change could otherwise trust
# its own reviewers.
_discover_load_trust() {
  local file="$1" project="$2" out=$'\n' n h _rest tdir pdir
  [ -f "$file" ] || { printf '%s' "$out"; return 0; }
  if [ -n "$project" ]; then
    tdir="$(cd -P "$(dirname -- "$file")" 2>/dev/null && pwd -P)"
    pdir="$(cd -P "$project" 2>/dev/null && pwd -P)"
    if [ -n "$tdir" ] && [ -n "$pdir" ]; then
      case "$tdir/" in
        "$pdir"/*)
          _discover_warn "ignoring trust file $file: it is inside the project under review"
          printf '%s' "$out"
          return 0
          ;;
      esac
    fi
  fi
  while read -r n h _rest || [ -n "$n" ]; do
    case "$n" in ""|"#"*) continue ;; esac
    [ -n "$h" ] || continue
    out="$out$n $(printf '%s' "$h" | tr 'A-F' 'a-f')"$'\n'
  done < "$file"
  printf '%s' "$out"
}

_discover_main() {
  local core_dir="" project_dir="" user_dir="$HOME/.cc-review/reviewers" body_dir=""
  local changed_file="" trust_file="$HOME/.cc-review/trusted-reviewers"
  CC_REVIEW_DISCOVER_PR=""
  CC_REVIEW_DISCOVER_SPEC=""
  CC_REVIEW_DISCOVER_SKIP_DETECTION="false"
  CC_REVIEW_DISCOVER_CHANGED=""
  CC_REVIEW_DISCOVER_TRUST=$'\n'
  CC_REVIEW_PROJECT_ROOT=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --core-dir) [ $# -ge 2 ] || { _discover_usage; return 1; }; core_dir="$2"; shift 2 ;;
      --project-dir) [ $# -ge 2 ] || { _discover_usage; return 1; }; project_dir="$2"; shift 2 ;;
      --user-dir) [ $# -ge 2 ] || { _discover_usage; return 1; }; user_dir="$2"; shift 2 ;;
      --pr) [ $# -ge 2 ] || { _discover_usage; return 1; }; CC_REVIEW_DISCOVER_PR="$2"; shift 2 ;;
      --spec) [ $# -ge 2 ] || { _discover_usage; return 1; }; CC_REVIEW_DISCOVER_SPEC="$2"; shift 2 ;;
      --changed-files) [ $# -ge 2 ] || { _discover_usage; return 1; }; changed_file="$2"; shift 2 ;;
      --trust-file) [ $# -ge 2 ] || { _discover_usage; return 1; }; trust_file="$2"; shift 2 ;;
      --body-dir) [ $# -ge 2 ] || { _discover_usage; return 1; }; body_dir="$2"; shift 2 ;;
      --skip-detection) CC_REVIEW_DISCOVER_SKIP_DETECTION="true"; shift ;;
      --verbose) CC_REVIEW_DISCOVER_VERBOSE="true"; shift ;;
      -h|--help) _discover_usage; return 0 ;;
      *) echo "Error: unknown argument: $1" >&2; _discover_usage; return 1 ;;
    esac
  done

  # "-" means "not provided" so callers can always pass the flag (zsh does not
  # split an unquoted ${x:+--flag "$x"} into two words).
  [ "$CC_REVIEW_DISCOVER_PR" = "-" ] && CC_REVIEW_DISCOVER_PR=""
  [ "$CC_REVIEW_DISCOVER_SPEC" = "-" ] && CC_REVIEW_DISCOVER_SPEC=""
  [ "$changed_file" = "-" ] && changed_file=""

  if [ -z "$core_dir" ]; then
    echo "Error: --core-dir is required" >&2
    _discover_usage
    return 1
  fi
  if [ ! -d "$core_dir" ]; then
    echo "Error: core directory not found: $core_dir" >&2
    return 1
  fi
  if [ -n "$changed_file" ] && [ ! -f "$changed_file" ]; then
    echo "Error: changed-file list not found: $changed_file" >&2
    return 1
  fi
  if [ -n "$body_dir" ] && { [ ! -d "$body_dir" ] || [ -n "$(ls -A "$body_dir" 2>/dev/null)" ]; }; then
    echo "Error: --body-dir must name an existing empty directory: $body_dir" >&2
    return 1
  fi
  local tool
  for tool in jq yq awk; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Error: $tool is required for reviewer discovery" >&2; return 1; }
  done
  # The frontmatter parser needs mikefarah yq v4 syntax; the Python yq and yq v3
  # would otherwise make every reviewer look "malformed".
  # "-" names stdin explicitly; yq 4.18 and 4.19 do not read stdin implicitly.
  if ! printf 'a: 1\n' | yq -o=json -I=0 '.' - >/dev/null 2>&1; then
    echo "Error: yq v4.18 or newer (https://github.com/mikefarah/yq) is required for reviewer discovery; found: $(yq --version 2>&1 | head -n 1)" >&2
    return 1
  fi
  if ! jq -n --rawfile x /dev/null --args 'true' -- >/dev/null 2>&1; then
    echo "Error: jq 1.6 or newer is required for reviewer discovery; found: $(jq --version 2>&1 | head -n 1)" >&2
    return 1
  fi
  CC_REVIEW_SHA256_TOOL=""
  for tool in sha256sum shasum openssl; do
    command -v "$tool" >/dev/null 2>&1 && { CC_REVIEW_SHA256_TOOL="$tool"; break; }
  done

  if [ -n "$project_dir" ]; then
    # The same logical spelling scan_layer uses, so changed paths (relative to
    # the git root) can be matched by prefix.
    CC_REVIEW_PROJECT_ROOT="$(CDPATH='' cd -- "$project_dir" 2>/dev/null && pwd)" || CC_REVIEW_PROJECT_ROOT=""
    # $(...) strips the closing newline of the framing; add it back.
    [ -n "$changed_file" ] && CC_REVIEW_DISCOVER_CHANGED="$(_discover_load_lines "$changed_file")"$'\n'
    [ "$CC_REVIEW_DISCOVER_CHANGED" = $'\n' ] && CC_REVIEW_DISCOVER_CHANGED=""
    CC_REVIEW_DISCOVER_TRUST="$(_discover_load_trust "$trust_file" "$project_dir")"$'\n'
  fi

  CC_REVIEW_BODY_DIR_OWNED=false
  if [ -n "$body_dir" ]; then
    CC_REVIEW_BODY_DIR="$(CDPATH='' cd -- "$body_dir" && pwd)" || return 1
  else
    local tmp_root="${TMPDIR:-/tmp}"
    tmp_root="${tmp_root%/}"
    if ! CC_REVIEW_BODY_DIR="$(mktemp -d "$tmp_root/cc-review-reviewers.XXXXXX")"; then
      echo "Error: cannot create a temporary directory under $tmp_root" >&2
      return 1
    fi
    CC_REVIEW_BODY_DIR_OWNED=true
  fi
  # On any failure path remove what this run created: the whole directory when
  # it made one, otherwise the files it wrote into the caller's directory.
  CC_REVIEW_DISCOVER_DONE=false
  trap '[ "$CC_REVIEW_DISCOVER_DONE" = true ] || { if [ "$CC_REVIEW_BODY_DIR_OWNED" = true ]; then rm -rf "$CC_REVIEW_BODY_DIR"; else find "$CC_REVIEW_BODY_DIR" -mindepth 1 -delete 2>/dev/null; fi; }' EXIT
  CC_REVIEW_DISCOVER_ROWS="$CC_REVIEW_BODY_DIR/.rows"
  CC_REVIEW_DISCOVER_RECORDS="$CC_REVIEW_BODY_DIR/.records.jsonl"
  : > "$CC_REVIEW_DISCOVER_ROWS"
  : > "$CC_REVIEW_DISCOVER_RECORDS"

  _discover_scan_layer "$core_dir/reviewers" "bundled"
  _discover_scan_layer "$user_dir" "user"
  [ -n "$project_dir" ] && _discover_scan_layer "$project_dir/.cc-review/reviewers" "project"

  # One final jq call: assemble elements, resolve overrides, sort, emit warnings
  local resolved
  if ! resolved="$(jq -n --rawfile rows "$CC_REVIEW_DISCOVER_ROWS" --slurpfile recs "$CC_REVIEW_DISCOVER_RECORDS" \
      --arg row_fields "$CC_REVIEW_ROW_FIELDS" '
    ($row_fields | split(" ")) as $names
    | ($rows | split("\n") | map(select(length > 0))
        | map(split("\u001f") as $vals
            | reduce range(0; $names | length) as $j ({}; .[$names[$j]] = (($vals[$j] // "") | gsub("\u000b"; "\n"))))) as $rows
    | [range(0; $rows | length) as $i
        | $rows[$i] as $r
        | ($r | .kind |= (if . == "" then null else . end)
              | .body_file |= (if . == "" then null else . end)
              | .reason |= (if . == "" then null else . end)
              | .refs |= (split("\u001e") | map(select(length > 0)))) as $m
        | if $m.status == "invalid" or $recs[$i] == null then
            { name: $m.name, kind: $m.kind, display_name: $m.name, category: null, enabled: null, requires: [],
              severity_map: {}, dedup: null, layer: $m.layer, path: $m.path, dir: null, body_file: null,
              references: [], context: [], command: null, overrides: null, status: "invalid", reason: $m.reason }
          else
            ($recs[$i] | del(.references_raw, .unknown_fields)
              | (if $m.parser_path != "" then .command.output.parser_path = $m.parser_path else . end))
            + { layer: $m.layer, path: $m.path, dir: $m.dir, body_file: $m.body_file, references: $m.refs,
                overrides: null, status: $m.status, reason: $m.reason }
          end]
    | reduce .[] as $r ({map: {}, order: [], invalid: [], changed: [], warnings: []};
        if $r.status == "invalid" then
          (if (.map[$r.name] // null) != null then " (falling back to the " + .map[$r.name].layer + " version)" else "" end) as $fb
          | .warnings += ["Warning: skipping reviewer " + $r.path + ": " + $r.reason + $fb]
          | .invalid += [$r]
        elif $r.status == "changed" then
          .changed += [$r]
        else
          (.map[$r.name] // null) as $prev
          | .map[$r.name] = ($r + {overrides: (if $prev != null then $prev.layer else null end)})
          | (if $prev == null then .order += [$r.name] else . end)
        end)
    # A project reviewer changed by the reviewed change never overrides: the
    # lower layer version runs, or the entry is listed as skipped.
    | reduce .changed[] as $r (.;
        if (.map[$r.name] // null) != null then
          .warnings += ["Warning: ignoring reviewer " + $r.path + ": changed in the reviewed change (using the " + .map[$r.name].layer + " version)"]
        else
          .warnings += ["Warning: ignoring reviewer " + $r.path + ": changed in the reviewed change"]
          | .map[$r.name] = ($r + {status: "skipped"})
          | .order += [$r.name]
        end)
    | . as $state
    | {
        warnings: .warnings,
        reviewers: (
          ([$state.order[] | $state.map[.]] + $state.invalid)
          | to_entries
          | sort_by(
              (if .value.status == "invalid" then 2 elif .value.status == "skipped" then 1 else 0 end),
              (if .value.layer == "bundled" then 0 elif .value.layer == "user" then 1 else 2 end),
              (if .value.kind == "command" then 1 else 0 end),
              .key)
          | map(.value))
      }')" || [ -z "$resolved" ]; then
    echo "Error: reviewer discovery could not assemble its result (jq error above)" >&2
    return 1
  fi
  rm -f "$CC_REVIEW_DISCOVER_ROWS" "$CC_REVIEW_DISCOVER_RECORDS"

  printf '%s' "$resolved" | jq -r '.warnings[]' >&2
  # Remove body files of entries that were overridden (keep the effective set only)
  local keep f
  keep="$(printf '%s' "$resolved" | jq -r '.reviewers[] | .body_file // empty')"
  for f in "$CC_REVIEW_BODY_DIR"/*.md; do
    [ -f "$f" ] || continue
    case "$keep" in
      *"$f"*) ;;
      *) rm -f "$f" ;;
    esac
  done
  # Nothing left for the caller (no valid reviewer): remove a directory this
  # run created. A caller-supplied directory stays; the caller removes it.
  [ "$CC_REVIEW_BODY_DIR_OWNED" = true ] && rmdir "$CC_REVIEW_BODY_DIR" 2>/dev/null
  CC_REVIEW_DISCOVER_DONE=true
  printf '%s' "$resolved" | jq '.reviewers'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  unset CDPATH
  _discover_main "$@"
fi
