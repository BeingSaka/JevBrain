# Antigravity CLI bridge — V2 integration

The user verified `agy 1.2.14` and `agy -p "Return exactly this text and nothing else: WORKER_OK" --model gemini-3.8-flash-low` on their Windows machine. This bridge relies on that observed non-interactive interface; no additional CLI flags, SDK, login or Gemini API key are assumed.

## Configure

Put these lines in your existing `.env`, preserving your TypeSafe key:

```dotenv
WORKER_COMMAND_JSON=["python","antigravity_worker.py"]
ANTIGRAVITY_MODEL=gemini-3.8-flash-low
```

Start the command from the extracted `jev-ai-evaluation-engine` directory. Keep the bridge in that directory next to `run.py`. The existing CommandWorker invokes Python without a shell; the bridge resolves `agy` from the PATH inherited by that process, then invokes it with `-p` and `--model` using an argv array. Relative paths follow the same project-directory convention as existing config/profile paths. If necessary set ANTIGRAVITY_EXECUTABLE to the native executable's absolute path; prefer forward slashes in Windows paths used inside JSON.

No Ollama configuration or GEMINI_API_KEY is required. Antigravity uses your existing signed-in account, subject to its quota. Actual quota/token usage is not available from the verified candidate-only CLI interface; it is not invented in logs.

## Final single end-to-end command

```powershell
python run.py .\examples\request-only.json --env-file .env --output result.json
```

This can perform generation plus up to two repairs according to the unchanged V2 policy. HUMAN REVIEW stops immediately; a worker does not override it. The sample task is small. No live Jev or Antigravity call was performed during bridge development.

## Compact prompts

Generation contains only original_request, locked_requirements, available_evidence, known_constraints and output_type. Configured deterministic constraints are folded into known_constraints so exact requirements are not lost.

Repair contains current previous_candidate, relevant failed dimensions, triggered rule IDs and their repair instructions, necessary existing locks and supplied evidence. Duplicate rule actions and dimension IDs already represented as rule feedback are removed. Exact constraints are folded into locks. The earlier preservation_reference is included only if V2 requests restoration of unnecessarily changed content; omitting it would prevent restoring lost correct content. Full Jev answers, probability tables, logs, history and unrelated rules are ignored.

Every repair includes:

> Repair only the identified failures. Preserve all already-correct content. Do not introduce unsupported information. Return only the corrected candidate.

Legacy V2 payloads without an operation marker are supported: failed_dimensions + previous_candidate implies repair; otherwise generation. Returned stdout is candidate text only. No model response wrapper or status message is added by the bridge.

## Safe failure behavior

Malformed JSON/fields, missing executable, timeout (90 seconds), nonzero exit, empty output and oversized response cause nonzero bridge exit with a safe stderr message and no candidate stdout. Provider stderr is never forwarded. V2 CommandWorker consequently stops the engine at HUMAN REVIEW. There are no bridge retries.

The bridge uses shell=False. Native Windows executables are supported. A `.cmd`/`.bat` launcher is rejected rather than passing arbitrary prompt text through Windows shell parsing; point ANTIGRAVITY_EXECUTABLE at a native executable if your installation resolves to a batch wrapper. This limitation was not observed in the user's reported command and has not been tested on their machine.

Command-line size is conservatively bounded to 30,000 UTF-16 code units; oversized prompts fail without truncation. The verified `-p` interface necessarily places the prompt in process arguments, visible to local process inspection. The bridge never includes API keys in prompts. It cannot reliably distinguish candidate text from banners the CLI might print, so it does not guess or strip content: `agy -p` must keep stdout candidate-only as in the supplied smoke test.

## Validation

62 tests passed: all 54 existing tests plus 8 bridge tests. Tests cover compact generation/repair payloads, preservation instruction, candidate-only stdout, missing executable, timeout, nonzero/empty results, malformed input, exact constraints, and engine HUMAN REVIEW following a bridge failure. All Antigravity executions were mocked or deliberately prevented by a nonexistent executable. No live cloud test was made.

Only added bridge/tests/documentation plus .env.example and README changes. Engine, evaluator, policy, thresholds, Failure Rules, CLI and maximum repair count are unchanged. No V3 features or additional dependencies.
