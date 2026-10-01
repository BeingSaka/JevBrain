# V2 worker integration completion

## Diagnosis

`configured_worker()` returns None when both `WORKER_COMMAND_JSON` and `OLLAMA_MODEL` are absent/blank. That produces `worker: "none"`; it is not a missing Jev connection. The user's live Jev validation is reported successful. It was not rerun during this worker task. Earlier historical V1/V2 validation documents describe the build sessions in which those credentials were not available.

A configured worker does not override policy. HUMAN REVIEW still stops without repair, including low Choice/Score confidence. Configuring a worker will not turn that outcome into REVISE. Thresholds and policy were not changed.

## Smallest implementation delta

Existing `CommandWorker` and `OllamaWorker` inherit a small provider-independent `AIWorker` base:

- `generate(payload) → candidate text`
- `repair(payload) → corrected candidate text`
- `run(payload)` remains the adapter transport and preserves existing fixtures/custom workers.

The engine invokes the appropriate operation; old workers exposing only `run()` remain supported. No additional provider, dependency, evaluator or policy engine was introduced.

Generation receives original request, locks, known constraints, evidence, output type and configured exact constraints; an optional initial comparison baseline is retained. Repair receives current candidate, failed dimensions, primary failure, only triggered blocking rule feedback and its instructions, evidence/exact constraints and restoration baseline where necessary. It does not receive evaluation history or the conversation.

Both adapters receive an `operation` marker. The explicit repair rule is enforced in the base repair payload and in the local Ollama system message:

> Repair only the identified failures. Preserve all content that already satisfies the request. Do not introduce unsupported information or unrelated changes.

Targeted feedback is assembled by existing `repair.py` from actual evaluation findings, not from generic improvement instructions. A semantic model's content preservation is an instruction and a rechecked condition, not a deterministic guarantee.

## Configure one worker

The existing environment mechanism is reused. Local Ollama is a free local route; it requires your Ollama server and an already installed model. No API credential for local Ollama is needed. This project does not download a model or purchase anything.

In `.env`:

```dotenv
TYPESAFE_API_KEY=your_existing_typesafe_key
OLLAMA_MODEL=your_exact_installed_local_model_name
OLLAMA_URL=http://localhost:11434
WORKER_COMMAND_JSON=
```

Replace the model placeholder with the actual name of an installed model. The Ollama server must be running. Do not include quotes as part of the key and do not share the file. Existing process environment values take precedence over `.env` values.

Alternative: use your already available worker program:

```dotenv
WORKER_COMMAND_JSON=["python", "my_worker.py"]
OLLAMA_MODEL=
```

Command configuration takes precedence. The program reads one JSON object from stdin and prints candidate text only on stdout. `operation` is `generate` or `repair`; the rest of the existing contract is retained. Any credentials for that chosen provider belong in environment variables. Do not use `fixture_worker.py` as a real AI worker. If that program uses a paid provider, its billing is separate; no paid provider was selected by this task.

## One end-to-end run

From the extracted project's directory, with your existing TypeSafe key and one real worker configured:

```powershell
python run.py .\examples\request-only.json --env-file .env --output result.json
```

That generates a candidate automatically, evaluates, repairs only on REVISE, and stops on PASS/HUMAN REVIEW. Supplied candidate mode remains:

```powershell
python run.py .\examples\input.json --env-file .env --output result.json
```

No worker call is made for a supplied candidate that passes or routes directly to HUMAN REVIEW. There are at most two repair attempts; unchanged candidates are not re-evaluated. A request-only run legitimately needs generation before a policy result exists.

## Worker usage logging

Result and evaluation logs now contain `worker_calls`, independently of Jev `usage`. Each call records operation, attempt, success/error status, elapsed time and optional usage counters. Ollama supplies `prompt_eval_count`, `eval_count` and `total_duration` (nanoseconds). These counters do not imply API charges. Command workers leave usage null unless a custom Python worker exposes `last_usage`; no breaking JSON response envelope is imposed on existing text-only command workers.

The list in evaluation history is cumulative for that run; count calls from the final result's list, not by summing every snapshot. Prompt/candidate content and provider credentials are not added to usage logs.

## Validation

**54 tests passed**: all 45 existing tests plus 9 worker integration tests. Tested clean PASS with zero worker calls; targeted FR003 repair/recheck/PASS; HUMAN REVIEW without worker calls; two failed repairs with no third; unchanged correct section in the preservation fixture; generation followed by evaluation; Ollama repair instruction and usage extraction; missing configuration; unchanged repaired output avoiding an extra Jev call.

The original V2 offline HTTP demo still completes three rule violations → targeted worker repair → PASS, and clean candidate → zero repairs. All test responses/repairs are explicit fixtures. They verify wiring and control flow, not model quality.

**Live worker test not performed:** this Work session has no TYPESAFE_API_KEY, OLLAMA_MODEL or WORKER_COMMAND_JSON. Your reported live Jev success is preserved as user-reported validation; the key on your Windows machine is not automatically available here. No expensive/repeated external test was attempted. The exact single run command is above.

## Changed files

Added: `tests/test_worker_integration.py`, this document.

Modified: `src/jev_engine/worker.py`, `engine.py`, `repair.py`, `README.md`, `.env.example`.

Jev client, Failure Rules Library, policy, thresholds, normalization and CLI unchanged. MAX_REPAIRS remains 2. No V3 features implemented.
