---
name: jevbrain-integration
description: >
  Use the JevBrain / JEV AI Evaluation & Decision Engine as an agent-facing
  quality gate. Activate when an agent must evaluate a candidate against locked
  requirements and evidence, decide whether it is safe to deliver, repair a
  clearly defective candidate through the configured worker, or stop for human
  review. This skill prepares JEV input, runs the existing CLI, interprets
  PASS/repair/HUMAN REVIEW outcomes, preserves locked requirements, and prevents
  bypassing JEV on uncertain or failed evaluations.
---

# JevBrain Agent Integration

Use this skill as a thin adapter over the existing JevBrain engine. Do not
reimplement evaluation logic inside the agent and do not replace the engine's
policy with subjective model judgment.

## Core contract

JevBrain is the source of truth for evaluation policy.

The agent owns:
1. collecting the user's request, locked requirements, evidence, and candidate;
2. converting that context into the documented JEV input JSON;
3. running the existing CLI;
4. interpreting the returned terminal decision;
5. delivering only when the engine returns `PASS`;
6. stopping when the engine returns `HUMAN REVIEW`.

The engine owns deterministic checks, failure rules, semantic evaluation,
policy thresholds, repair routing, retry limits, and final decision.

Do not create a second scoring system in this skill.

## Activation

Use this skill when any of the following is true:

- a candidate output must be checked against explicit requirements before delivery;
- an agent-generated artifact needs an independent JEV gate;
- a candidate may contain unsupported claims, missing requirements, contradictions,
  format violations, or scope creep;
- a worker should repair a clearly actionable defect;
- the workflow explicitly requires PASS / repair / HUMAN REVIEW control.

Do not use this skill merely to brainstorm, summarize, or answer ordinary
low-risk questions when no JEV gate was requested.

## Input preparation

Build one JSON object matching the repository input contract.

Required:

- `original_request`: non-empty string containing the task to be evaluated.

Use when known:

- `locked_requirements`: requirements that must not be silently relaxed;
- `candidate_output`: candidate text to evaluate;
- `output_type`: label such as `text`, `json`, or another documented type;
- `available_evidence`: evidence the candidate may rely on;
- `known_constraints`: additional constraints;
- `previous_candidate`: prior version when comparison is required;
- `allowed_changes`: explicit change boundaries;
- `deterministic_checks`: exact machine-checkable rules.

Do not invent evidence, requirements, product facts, prices, certifications,
origins, or other task facts that were not supplied by the user or trusted
source.

Prefer deterministic checks for exact constraints:

```json
{
  "required_substrings": ["required phrase"],
  "forbidden_substrings": ["forbidden phrase"],
  "max_chars": 200,
  "valid_json": false,
  "json_required_fields": ["field_name"]
}
```

Substring checks are exact and case-sensitive.

For semantic requirements, use `locked_requirements` and
`known_constraints`; do not attempt to emulate JEV with regexes or prompt
heuristics.

## Candidate modes

### Evaluate supplied candidate

If the agent already has a candidate, populate `candidate_output` and run JEV.

### Generate then evaluate

If `candidate_output` is absent or null, JevBrain may call the configured
worker to generate it. This requires a working worker configuration.

Do not claim generation is available unless the worker is configured and
actually executable.

## Execution

Run from the JevBrain repository root.

Typical live evaluation:

```bash
python run.py <input.json> --env-file .env --output <result.json>
```

On Windows, `py` may be used instead of `python`.

When the task requires the full Noul + Choice + Score semantic pipeline, use:

```bash
python run.py <input.json> --env-file .env --output <result.json> --semantic
```

Default failure rules are loaded from `rules/universal.json`.

Do not add `--no-rules` unless the user explicitly wants V1 behavior without
the Failure Rules Library.

Do not expose API keys or paste them into prompts or generated files.

## Decision handling

Read the engine result JSON, not only the process exit code.

### PASS

If `decision == "PASS"`:

- the candidate passed the configured JEV gates;
- delivery may continue;
- describe PASS as configured probabilistic acceptance, not proof of truth.

### Repair path

The engine uses `REVISE` internally for a clear, actionable failure and can
invoke the configured worker for targeted repair. REVISE is not a terminal CLI
decision.

For human-facing agent workflows, this may be presented as **REPAIR in
progress** while the engine is performing its bounded repair cycle.

Do not manually override the engine's repair target or silently rewrite locked
requirements.

The engine permits at most two repairs and stops repeated or unchanged outputs
rather than looping indefinitely.

### HUMAN REVIEW

If `decision == "HUMAN REVIEW"`:

- stop automatic delivery;
- do not reinterpret the result as a weak PASS;
- do not keep repairing outside the engine's bounded repair policy;
- show the engine-provided reason;
- preserve the candidate and result for human inspection.

Typical causes include uncertainty, insufficient evidence, unavailable provider
or worker, malformed input/configuration, or failures that cannot be repaired
responsibly.

## Exit-code handling

The current CLI returns:

- exit code `0` for terminal `PASS`;
- exit code `2` for terminal non-PASS outcomes and input/configuration errors.

Therefore, do not infer HUMAN REVIEW solely from exit code 2. Read the JSON
result or stderr payload and preserve its exact terminal decision/reason.

## Presentation contract

For agent-facing output, keep the first layer simple:

```text
JEV: PASS
```

or

```text
JEV: HUMAN REVIEW
Reason: <engine reason>
```

When a repair occurred and the final result is available, show:

```text
JEV: <final decision>

Before:
<previous candidate>

After:
<final candidate>

What changed:
- <only changes supported by the engine history / deterministic diff>
```

Do not invent a textual critique that JEV did not produce. The evaluator returns
typed judgments and policy decisions; repair instructions are assembled by code.

Technical details such as failed dimensions, primary failure, scores,
probabilities, confidence, rule findings, repair count, elapsed time, and usage
may be exposed progressively when present in the result.

## Non-bypass rules

Never:

- deliver a candidate after HUMAN REVIEW as though JEV passed it;
- change locked requirements to obtain PASS;
- fabricate missing evidence;
- suppress a blocking failure rule;
- retry indefinitely;
- substitute the agent's own confidence for JEV policy;
- treat a high aggregate score as overriding a failed blocking judgment;
- claim a live evaluation occurred when only offline fixtures/tests ran.

## Failure behavior

If JEV cannot run because files, configuration, credentials, provider access, or
worker access are unavailable:

1. report the exact verified blocker;
2. do not fabricate an evaluation;
3. do not mark the candidate PASS;
4. preserve the prepared input so the run can be resumed.

The engine intentionally fails closed to HUMAN REVIEW for invalid or unavailable
configuration.

## Validation before delivery

Before saying the integration succeeded, verify all applicable items:

- the input JSON matches the documented contract;
- locked requirements were preserved;
- exact checks were encoded deterministically where possible;
- the CLI executed from the repository root;
- the expected result file was written when `--output` was used;
- terminal decision was read from result JSON;
- no secret was printed or committed;
- HUMAN REVIEW stopped delivery;
- any repair stayed within the engine's bounded repair cycle.

For repository-level changes, also run the existing offline test suite:

```bash
python -m pytest tests/
```

or:

```bash
python -m unittest discover -s tests -v
```

Do not present offline tests as proof of live TypeSafe or live worker
connectivity.

## Architecture boundary

Keep JevBrain core separate from agent integrations.

```text
Agent / Coding Tool
        |
        v
jevbrain-integration skill
        |
        v
existing JevBrain CLI / engine
        |
        +--> deterministic checks
        +--> failure rules
        +--> Jev semantic evaluation
        +--> policy
        +--> configured worker repair
        |
        v
PASS / HUMAN REVIEW
```

REVISE remains an internal engine routing state; human-facing integrations may
label the active bounded correction phase as REPAIR without changing engine
semantics.

Do not add provider-specific behavior to the core engine merely to support one
agent. Provider- or agent-specific hooks belong in separate adapters.
