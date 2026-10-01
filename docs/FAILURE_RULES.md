# V2 — Failure Rules Library

This is an extension of the V1 engine. Same client, profile, policy entry point, worker, JSONL logger and maximum two repairs. No additional dependencies or independent evaluator.

## Use

The CLI loads `rules/universal.json` by default:

```bash
python run.py examples/input.json --env-file .env --output result.json
python examples/demo_v2.py
python -m unittest discover -s tests -v
```

Disable rules to reproduce V1 evaluation:

```bash
python run.py examples/input.json --env-file .env --no-rules
```

Explicitly combine packs (explicit `--rules` paths replace the default list):

```bash
python run.py examples/input.json --env-file .env --rules rules/universal.json --rules rules/my-rules.json
```

The Python API accepts an optional `rules=` argument on the original `Engine`. Omission preserves V1 evaluation. Load JSON packs with `failure_rules.load_packs(paths, profile)`.

## Rule schema

A pack contains `schema_version: 1`, a nonempty `pack_id`, and a `rules` array. Every rule uses this exact schema; unknown/missing fields and duplicate IDs are rejected:

```json
{
  "rule_id": "CUSTOM001",
  "name": "Unrequested sales pitch",
  "description": "Avoid an unsolicited sales pitch in the requested answer.",
  "category": "instruction_violation",
  "severity": "WARNING",
  "detection_question": "Does candidate_output contain an unsolicited sales pitch outside original_request?",
  "true_criteria": "An unrequested sales pitch materially expands or distracts from the task.",
  "false_criteria": "No sales pitch, or the user explicitly requested one.",
  "enabled": true,
  "applicable_types": ["*"],
  "requires_previous_candidate": false,
  "detector": {"kind": "noul"},
  "repair_instruction": "Remove only the unrequested sales pitch; preserve the requested answer."
}
```

Use a unique ID matching `[A-Za-z][A-Za-z0-9_-]{0,63}`. `applicable_types` matches `output_type` exactly; `*` covers all tasks. Severity must be INFO, WARNING or CRITICAL. Category is a descriptive string; it does not require adding a Choice option or changing policy code.

### Detector options

| Detector | Behavior |
|---|---|
| `{"kind":"noul"}` | Add one explicit Noul to the existing mixed request |
| `{"kind":"reuse","question_id":"unsupported_claim_present"}` | Reuse the already returned V1 Noul; no extra judgment |
| `{"kind":"deterministic","check_id":"json_required_fields"}` | Use a supported exact code check; no Jev question |
| `{"kind":"noul","check_ids":["valid_json","json_required_fields","max_chars"]}` | Exact failures override semantic detection; otherwise evaluate semantic format conditions |

Reuse rules must copy the existing Noul's `instructions` and true/false criteria **exactly** into their schema. This prevents changing the rule description while silently evaluating different criteria. New/changed semantic criteria should use `kind: noul`.

Supported deterministic IDs: candidate_empty, required_substrings, forbidden_substrings, max_chars, valid_json, json_required_fields. A deterministic-only rule is applicable only if its check is configured, except candidate_empty, which always runs. Future packs can use these existing check primitives without engine changes; arbitrary new executable detectors are not supported by configuration.

Exact JSON-key requirement input:

```json
"deterministic_checks": {"json_required_fields": ["message", "launch_date"]}
```

These are required **top-level** keys, not dotted paths or a full JSON Schema validator. Malformed JSON or a non-object also fails. Deterministic failures skip the Jev call and request targeted correction through the original V1 flow.

## Starter rules

| ID | Rule | Severity | Detection |
|---|---|---|---|
| FR001 | Missing explicit mandatory requirement | CRITICAL | Reuse critical_requirement_missing |
| FR002 | Locked requirement violated | CRITICAL | Noul |
| FR003 | Unsupported/invented claim | CRITICAL | Reuse unsupported_claim_present |
| FR004 | Internal/evidence contradiction | CRITICAL | Reuse internal_contradiction_present |
| FR005 | Unnecessary generic/filler content | WARNING | Noul |
| FR006 | Explicit format violated | CRITICAL | Exact format failures first; Noul for semantic format |
| FR007 | Correct existing content unnecessarily changed | CRITICAL | Noul, only with previous candidate |
| FR008 | Important uncertainty presented as certainty | CRITICAL | Noul |
| FR009 | Scope creep | CRITICAL | Noul |
| FR010 | Material repetition/redundancy | WARNING | Noul |

Initially the default pack adds six Nouls to V1's nine questions (15 total). After a repair or with a supplied comparison candidate it adds FR007 (16 total). All questions share the same HTTP request. Choice remains the existing primary failure class; Score remains the existing five-level readiness rubric. Rule IDs provide specific feedback when independently judged violations coexist; Choice is not expected to enumerate all failures.

## Policy interaction

Existing V1 decisions are computed first. Existing HUMAN REVIEW remains HUMAN REVIEW; rule findings never downgrade it to an automatic repair. Rules do not weaken any V1 gate.

For active semantic rules, use V1's configured `risk_max` (default 0.10) and `failure_min` (default 0.80):

| Probability | Status | WARNING / CRITICAL | INFO |
|---|---|---|---|
| ≤ risk_max | clear | No added restriction | No added restriction |
| > risk_max and < failure_min | uncertain | HUMAN REVIEW | Advisory |
| ≥ failure_min | triggered | Blocks PASS; REVISE if the base policy permits automatic action | Advisory |

Exact checks produce 0/1 deterministic indicators, **not Jev probabilities**. Their method is explicitly labelled in logs. V1's exact checks independently remain hard gates, even if a rule referencing them is set to INFO.

Thus a CRITICAL rule at 0.99 blocks PASS even with Score=4 and Choice=none. Missing worker, exhausted repairs, uncertain evidence or low base confidence still yield HUMAN REVIEW. A triggered rule carries its own actionable correction, so an otherwise passing Choice `none` does not prevent a rule-based REVISE. INFO does not by itself cause rewriting. WARNING blocks at the same probability thresholds as CRITICAL in this minimal release; severity remains recorded for prioritization and future calibration.

## Targeted repair and preservation

Repair includes only triggered WARNING/CRITICAL rule feedback: rule ID, name, severity, probability and repair instruction. Clear, uncertain and INFO rules are excluded. Existing failed dimensions remain included. All unaffected content must be preserved; the engine never instructs full regeneration merely because a rule failed.

Before each recheck the engine supplies `previous_candidate` and `repair_context` (identified defects and required corrections). FR007 judges whether previously correct, unaffected content was unnecessarily changed. If FR007 triggers, the worker also receives `required_correction.preservation_reference` containing the earlier comparison candidate; the current failed candidate alone would be insufficient to restore lost content.

For an initial edit evaluation, optionally supply:

```json
"previous_candidate": "The earlier version to compare against.",
"allowed_changes": ["Correct only the launch date."]
```

Without a baseline, FR007 is skipped, not labelled clear. User `allowed_changes` governs the supplied initial comparison; later automatic repairs use their own specific repair context rather than renewing broad permissions.

## Logging

Existing JSONL events gain:

- `rule_library_sha256`
- `rule_findings`: ID, name, severity, category, status, method, probability, policy impact, applicable repair instruction and repeated_after_repair
- `triggered_rule_ids`
- `repair_requested`: whether this evaluation routed to repair
- `repair_performed`: whether the candidate in this event came from a successful worker repair
- `repaired_from_rule_ids`: rule feedback supplied for that prior repair

Recurrence compares against earlier triggered IDs in the same run after repairs. It is not a global historical counter. Cross-run trends can later be computed from JSONL without adding a database. Skipped semantic rules on deterministic failures have no findings; absence means not evaluated, not a false/zero result. A failed repair can be distinguished from a requested repair by the subsequent error event and `repair_performed: false`.

No candidate text or secrets were added to log content. Comparison text is sent to Jev/worker when needed; retain your existing sensitive-data precautions.

## Add a rule later

1. Copy the example into a pack with `schema_version`, `pack_id`, and `rules`.
2. Assign a unique ID, explicit positive/negative criteria, severity, applicability and targeted repair instruction.
3. Choose semantic Noul, exact deterministic check or exact-semantic reuse.
4. Pass the pack with repeatable `--rules`. Core code does not change.
5. Test a violating and clean example before relying on it. Disabling/removing a rule does not disable overlapping V1 hard gates.

No domain packs are implemented in V2.

## Validation and limits

45 tests passed: all 26 original V1 tests plus 19 V2 tests. Offline HTTP demo deliberately violates locked date, filler and scope; FR002/FR005/FR009 → REVISE → worker receives only those rule instructions → recheck → PASS. A separate clean candidate passes with zero repairs. Additional tests cover recurrence, two-repair cap, exact JSON fields, uncertainty, advisory INFO, disabled/task-scoped rules, future pack loading and preservation reference delivery.

Demo probabilities and repair output are scripted fixtures. **Live Jev semantic detection and real AI repair remain NOT VERIFIED** because the session has no credentials/worker. Tests prove integration and routing, not detection accuracy.

Rule probabilities and thresholds remain uncalibrated. Jev cannot return exact failing spans; feedback identifies rule IDs and correction intent, not a quoted localized defect. Preservation is a semantic judgment against a previous version and authorized corrections, not proof that every previous sentence was correct. More questions and repair comparison context increase input-token usage; batching and three reused judgments limit duplication. Large packs can hit the existing context guard; no automatic truncation or silent pack dropping occurs.
