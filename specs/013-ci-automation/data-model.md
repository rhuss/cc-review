# Data Model

- Config: schema_version=1; enabled boolean; triggers {pr_opened,pr_synchronize,issue_opened,comments,sweep,dispatch}; commands {review,triage,assess,fix,help}; command_permissions nonempty subset read/triage/write/maintain/admin; identity.bot_login; provider/model strings; labels mapping pursue/needs_evidence/direction/decline to nonempty label names; limits sweep 1..100, turns 1..100, timeout 1..60 minutes, diff_bytes 1..1000000.
- Request: positive item number, operation review/triage/assess/fix/help, source event/comment/sweep/dispatch, actor and current permission. Workers refresh target type, fork, head and authorization.
- Snapshot: item, comments, threads, checks, diff; completeness required. Review fingerprint=head. Triage fingerprint=head+non-self thread activity. Assessment fingerprint=body/title+non-self issue conversation. Status changes do not invalidate themselves.
- Status: schema=1, per-operation entries {fingerprint,state,run_id,run_url,updated_at,reason}; running -> completed/skipped/needs_attention. Running expires at timeout+300 seconds. Only completed matching fingerprints suppress work.
- Proposal: status completed/skipped/needs_attention, reason, body, labels (assessment classification keys), replies [{thread_id,body,resolve,evidence}], files [{path,content}]. Unknown or mismatched mutation fields fail closed.
- Managed setup: caller with management sentinel and immutable integration ref, JSON-compatible YAML configuration, optional manifest; no secret values.
