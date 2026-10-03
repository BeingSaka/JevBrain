**Antigravity bridge added:** Use `WORKER_COMMAND_JSON=["python","antigravity_worker.py"]` and `ANTIGRAVITY_MODEL=gemini-3.8-flash-low` in your existing `.env`. No Ollama or Gemini API key required. Run from this project directory. Setup and limits: [docs/ANTIGRAVITY_BRIDGE.md](docs/ANTIGRAVITY_BRIDGE.md). 62 tests pass; no live Antigravity/Jev call was made during this change.

**Worker integration completed:** Explicit provider-independent `generate()` / `repair()` operations now use the existing local Ollama or command adapter. Setup, targeted feedback, usage logs and the single live run command: [docs/WORKER_INTEGRATION.md](docs/WORKER_INTEGRATION.md). All 54 tests pass. User-reported live Jev validation succeeded; live worker validation is still pending configuration.

# JEV AI Evaluation & Decision Engine — V2

**V2 delta:** The configurable universal Failure Rules Library plugs into the existing V1 engine. Ten starter rules; no new dependencies. CLI defaults to `rules/universal.json`; `--no-rules` preserves V1 evaluation. Full schema, severity policy, extension instructions and validation: [docs/FAILURE_RULES.md](docs/FAILURE_RULES.md).

```bash
python examples/demo_v2.py
python run.py examples/input.json --env-file .env --output result.json
```

Python 3.10+; standard library only. Universal evaluator with automatic targeted repair.

**Original V2 build was tested offline. The user subsequently reported successful live Jev evaluation. This Work session has not run a live AI worker: worker configuration and credentials are unavailable here.** The demo uses explicit HTTP/worker fixtures; it does not establish evaluator accuracy.

## Architecture

JSON input → normalize → optional AI worker generation → deterministic checks → one TypeSafe request (7 base Noul + 1 Choice + 1 Score, plus active failure-rule Nouls) → application policy → PASS / REVISE / HUMAN REVIEW.

REVISE → targeted worker correction → checks and Jev re-evaluation. At most **two repairs**, normally at most **three Jev evaluations**. Unchanged/previously seen output stops immediately without another Jev request. Deterministic failures skip Jev. API failures, missing worker, unresolved evidence and uncertainty stop at HUMAN REVIEW. A PASS is a configured probabilistic acceptance, never proof of truth.

## Setup and run

Extract this project and open a terminal **inside `jev-ai-evaluation-engine`**. No pip installation is required for the engine runtime.

### 1. Environment file

Copy `.env.example` to `.env`:

```powershell
# PowerShell
Copy-Item .env.example .env
```
```bash
# bash / zsh
cp .env.example .env
```

Open `.env` and set `TYPESAFE_API_KEY`. The `.env.example` file documents every supported variable with inline comments.

### 2. TypeSafe API key (required for live evaluation)

Obtain a key at https://console.typesafe.ai and set `TYPESAFE_API_KEY` in `.env`. Do not paste credentials into chat. The client uses `POST https://api.typesafe.ai/v1/systemone` only. Keys for independent Jev community gateways are not interchangeable; V1 does not send keys to those services.

### 3. Worker (optional)

A worker generates and repairs candidates. Without one the engine evaluates supplied candidates only — no AI generation or repair cycles run.

Three options, documented in `.env.example` and `docs/WORKER_INTEGRATION.md`:

- **Antigravity CLI (`agy`):** Set `WORKER_COMMAND_JSON=["python","antigravity_worker.py"]`. Requires the `agy` executable on `PATH` and an active Antigravity account. The native binary must be used; `.bat`/`.cmd` launchers are not supported. See `docs/ANTIGRAVITY_BRIDGE.md`.
- **Ollama (local, free):** Set `OLLAMA_MODEL` to an **already installed** Ollama model and start the Ollama server. `OLLAMA_URL` defaults to `http://localhost:11434`. The engine does not download models.
- **Custom command:** Set `WORKER_COMMAND_JSON` to a JSON argv array pointing to your own worker program (reads JSON from stdin, writes candidate text to stdout).

`WORKER_COMMAND_JSON` takes precedence over `OLLAMA_MODEL` if both are set.

### 4. Install test dependency (optional)

```bash
pip install -r requirements.txt
```

This installs `pytest`. The engine itself has no runtime pip dependencies.

### 5. Run tests

```bash
python -m pytest tests/
```

Or without pytest:

```bash
python -m unittest discover -s tests -v
```

All tests run fully offline without credentials.

### 6. Offline demo (no credentials required)

```bash
python examples/demo.py
python examples/demo_v2.py
```

Both demos use explicit HTTP and worker fixtures. Output is labelled `OFFLINE FIXTURES`. This verifies control flow, not live Jev accuracy.

### 7. Live CLI run

With a supplied candidate (intentionally defective — HUMAN REVIEW or REPAIR is the expected result):

```bash
python run.py examples/input.json --env-file .env --output result.json
```

`examples/input.json` contains a candidate that invents a price and omits the required launch date. **HUMAN REVIEW or REPAIR is the correct outcome**, not a sign of misconfiguration.

With request-only mode (worker required; engine generates and evaluates):

```bash
python run.py examples/request-only.json --env-file .env --output result.json
```

`python` may be `py` on Windows. No activation or editable installation is needed beyond `requirements.txt`. CLI exit code 0 = PASS; 2 = HUMAN REVIEW or input/configuration error. REVISE is an intermediate logged decision, never a terminal CLI result. `result.json` contains the final output, decision, reason, repair count and evaluation history. Evaluation logs default to `logs/evaluations.jsonl`.

Environment variables override `.env`. `--env-file` explicitly loads a simple `KEY=value` format, without shell interpolation; it is not a complete dotenv parser.

### 8. Semantic evaluation default and flags

Semantic Noul + Choice + Score evaluation is **enabled by default**. Normal execution requires no semantic flag:

```bash
python run.py examples/input.json --env-file .env
```

- `--semantic` remains accepted as an explicit redundant enable flag.
- `--no-semantic` explicitly selects the legacy non-semantic path.

The benchmark runner (`benchmarks/run_benchmark.py`) always uses the semantic pipeline regardless of these flags.

### 9. Benchmark

The canonical 36-case Noul Benchmark v1.0 measures the engine against labeled gold cases:

```bash
python benchmarks/run_benchmark.py
```

Requires `TYPESAFE_API_KEY` in `.env`. The runner validates the canonical fixture SHA before every run. Results are saved to `benchmarks/baseline_results.json`.

**Cache:** The runner caches provider responses in `benchmarks/.api_cache.json` (gitignored). Cached cases are replayed without a live provider call — the output indicates `Noul:` values but does not re-contact the API. To force a fully fresh live run, delete `benchmarks/.api_cache.json` before running:

```powershell
Remove-Item benchmarks\.api_cache.json -ErrorAction SilentlyContinue
```

Validate the fixture without running a full benchmark:

```bash
python benchmarks/validate_fixture.py
```

## Worker contract (no routine copy/paste)

A command worker receives one JSON object on stdin and writes **only candidate text** to stdout. Exit nonzero on failure; diagnostic text belongs on stderr. The engine never invokes a shell or interpolates candidate text into command arguments. It runs only the configured executable/argv, not commands found in the candidate.

For a generation call: `original_request`, `locked_requirements` (includes known constraints), `available_evidence`, `output_type`, `deterministic_constraints`.

For a repair call: `original_request`, `locked_requirements`, `previous_candidate`, `failed_dimensions`, `primary_failure`, `required_correction`. Evidence and exact deterministic constraints are nested in `required_correction`, so repair needs no external copy/paste.

Example configuration for an existing worker script:

```dotenv
WORKER_COMMAND_JSON=["python", "my_worker.py"]
```

Provide your own AI implementation in that script; **`examples/fixture_worker.py` is a test fixture, not an AI worker**. The bundled Ollama adapter is the ready-to-use local AI path. No extra paid model provider is introduced. A command adapter using a paid provider would incur that provider's separate charges and must be chosen deliberately. Workers inherit environment variables for their own credentials; use only trusted worker executables.

## Input contract

See `examples/input.json`. Required: nonempty `original_request`. Optional `candidate_output`: a string, or absent/null to generate with the worker. Empty candidate text is a deterministic defect, not an excuse to call Jev.

Optional fields: `locked_requirements` and `known_constraints` are lists of strings; `output_type` is a label (default `text`); `available_evidence` is a string (default empty). Optional V2 `previous_candidate` and `allowed_changes` enable comparison against an earlier version. Other unknown fields are rejected to prevent accidental context expansion. Multimodal evidence must first be converted into textual observations by an external perception layer; this engine does not inspect media.

Optional `deterministic_checks` supports:

```json
{
  "required_substrings": ["Atlas"],
  "forbidden_substrings": ["guaranteed"],
  "max_chars": 200,
  "valid_json": false,
  "json_required_fields": ["message", "launch_date"]
}
```

Substring checks are exact and case-sensitive. `max_chars` counts Python Unicode characters, not bytes or grapheme clusters. JSON validation rejects NaN/Infinity. `json_required_fields` checks exact top-level keys in a JSON object. Put exact checks here, and semantic requirements in the locked lists. The engine does not infer regex rules, execute candidate code, or run arbitrary tests automatically.

## Evaluation and routing

`evaluators/universal.json` defines explicit true/false criteria for:

- requirements_met
- critical_requirement_missing
- instruction_violation_present
- internal_contradiction_present
- unsupported_claim_present
- evidence_sufficient
- ready_to_deliver

Choice classifies the primary failure as none, missing_requirement, instruction_violation, contradiction, unsupported_claim, insufficient_evidence, generic_output, format_violation or other.

Score uses five ordered levels: 0 unusable; 1 major revision; 2 acceptable with issues; 3 strong; 4 production ready. The API score is probability-weighted and may be fractional; it is not an objective grade.

`config/thresholds.json` holds **uncalibrated starting thresholds**:

| Gate | Default |
|---|---:|
| Positive Noul acceptance | ≥ 0.90 |
| Negative Noul risk acceptance | ≤ 0.10 |
| Clear failed judgment | ≥ 0.80 failure probability |
| Score acceptance | ≥ 3.50 on 0–4 |
| Choice and Score confidence | ≥ 0.65 |

PASS requires every acceptance gate plus Choice `none`. A strong score cannot override a failed Noul. Low confidence or a failed Noul in its uncertainty band yields HUMAN REVIEW. REVISE requires clear failures and an actionable Choice category. Missing evidence/`other` goes to HUMAN REVIEW because the worker cannot responsibly fabricate a correction. A failed V1 gate paired with Choice `none` also requires review. Additional V2 blocking rule findings can turn a base PASS into REVISE or HUMAN REVIEW; see the rule policy document.

The evaluator cannot return textual critique. Repair instructions are assembled by code from failed dimensions, class, original constraints and supplied evidence. They identify the failed areas but do not claim to pinpoint a sentence Jev never identified.

## Logging, errors and usage

JSONL records UTC timestamp, run ID, task type, worker, evaluator/profile, profile hash, thresholds, state/candidate hashes, raw typed results, model version, policy decision, failed dimensions, reason, repair count, elapsed time, token usage and an estimated TypeSafe charge. No API key, request text, candidate text, provider error body or worker stderr is logged. Retain your input and result files if you want to label failures for later calibration; hashes correlate the corresponding artifacts. Treat your own input/result files as sensitive.

Malformed/missing answers, types, distributions, scores or usage are rejected. HTTP 429/529 get up to two transport retries with bounded exponential backoff; Retry-After is honored up to 10 seconds. Larger delays stop for review. Other HTTP errors, connection failures and timeouts stop without retries. Timeout requests may still have been billed by the provider. Redirects are refused to avoid forwarding bearer credentials. Logs must be writable; a log failure stops execution. Repair cycles and HTTP transport attempts are independent counters.

## Verified API surface (2026-10-01)

Official sources and compatibility mapping are in `docs/API_VERIFICATION.md`.

- Direct API supports structured state and all three question types in one request. Python and JS SDKs exist; direct standard-library HTTP keeps V1 dependency-free.
- Stable model pinned to `jev-1.13.0`. `jev-latest` is configurable but may change probabilities across releases.
- Official published price: **$0.042 per million input tokens**, output free. An evaluation using 10,000 input tokens is approximately $0.00042; three such evaluations approximately $0.00126. These are arithmetic examples, not measured V1 usage or account balance promises.
- Published limits: 100K tokens/second, 40 requests/second, subject to dynamic adjustment. Context: 64K total tokens; 32K state + longest question.
- V1 conservatively guards serialized UTF-8 byte sizes (30,000 state+longest-question; 60,000 total), instead of silently truncating or pretending to have the official tokenizer. This may reject otherwise valid long inputs. Shorten explicitly.
- Existing credits, free grants, account-specific quota and balance could not be verified without your account. No credit purchase or third-party service was introduced.

## Validation and limitations

45 automated tests passed at V2 build time (26 original V1 tests + 19 V2 tests). Offline HTTP demo: REVISE → fixture correction → PASS, one repair and two HTTP evaluations. Tests cover initial generation, cap exhaustion, uncertainty, hard-gate precedence, evidence review, invalid responses, unchanged/oscillating candidates, deterministic validation, auth/retries and command execution.

**Live worker acceptance is pending**; the user has since reported successful live Jev evaluation. To validate with real Jev and an actual worker, run the commands above with your local credentials and worker. A terminal HUMAN REVIEW can be the correct outcome, not a failed integration.

Universal judgments are broad and uncalibrated. Supplied evidence is not independently researched or authenticated. Jev can be steered by adversarial content despite explicit data-boundary instructions; no claim of prompt-injection immunity. English accuracy is strongest per the vendor; Marathi/Hindi performance needs measured validation. The engine does not attach itself to ordinary ChatGPT/Gemini web conversations; it integrates through an automated worker adapter or a supplied candidate. Offline fixtures demonstrate control flow, not the probability quality of Jev or the quality of a local model.

## Project structure

```text
jev-ai-evaluation-engine/
  run.py                        entry point (python run.py <input> --env-file .env)
  antigravity_worker.py         Antigravity CLI worker bridge
  README.md
  .env.example                  template; copy to .env
  requirements.txt              runtime: stdlib only; dev: pytest
  config/thresholds.json        acceptance thresholds (calibrated per session)
  evaluators/universal.json     Jev question criteria
  rules/universal.json          Failure Rules Library (10 starter rules)
  src/jev_engine/
    __init__.py
    __main__.py                 CLI argument parsing
    normalize.py
    jev_client.py               TypeSafe HTTP client
    policy.py                   decision routing
    repair.py                   repair payload assembly
    worker.py                   OllamaWorker, CommandWorker, configured_worker()
    engine.py                   Engine orchestrator
    semantic.py                 semantic_decide() policy engine
    logging.py
    failure_rules.py            load_packs(), findings_for()
  tests/
    test_engine.py
    test_failure_rules.py
    test_semantic.py
    test_client_validation.py
    test_worker_integration.py
    test_antigravity_worker.py
  benchmarks/
    run_benchmark.py            36-case canonical benchmark (requires TYPESAFE_API_KEY)
    validate_fixture.py         offline fixture integrity check
    noul_benchmark_v1_locked.json  immutable canonical fixture
    noul_benchmark_v1_integrity.txt  expected SHA and case manifest
  examples/
    input.json                  sample with intentionally defective candidate
    request-only.json           request-only mode (worker generates candidate)
    demo.py                     offline V1 control-flow demo
    demo_v2.py                  offline V2 demo with Failure Rules
    fixture_worker.py           test fixture only; not a real AI worker
  docs/
    API_VERIFICATION.md
    FAILURE_RULES.md
    WORKER_INTEGRATION.md
    ANTIGRAVITY_BRIDGE.md
    VALIDATION.md
    V2_VALIDATION.md
    LOCKED_HANDOFF.md
  logs/                         created on first run; gitignored
```

## Future work (not implemented)

Calibrate thresholds from labeled real usage; measure false passes and unnecessary reviews. Add per-requirement localization if aggregate failure instructions prove too broad. Add your preferred worker's native adapter only after selecting the actual automation surface and confirming its costs. Introduce domain profiles after the universal flow is measured. Add model-upgrade comparison and optional secure state capture for calibration. No databases, dashboards, agents or separate primitive skills are needed for V1.
