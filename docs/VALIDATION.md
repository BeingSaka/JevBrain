# Validation log

## V1 (original build — 2026-10-01)

- `python -m unittest discover -s tests -v`: **26/26 passed**.
- `python examples/demo.py`: local HTTP contract fixture + subprocess worker fixture → REVISE → PASS; exactly one repair and two evaluations. `demo-result.json` contains the summary.
- `python run.py examples/input.json --output result.json`: **HUMAN REVIEW**, `TYPESAFE_API_KEY is not configured`, zero repairs, CLI exit 2; logged safely without credentials.
- TypeSafe payload/response schema checked against current official API reference.
- Local Ollama HTTP adapter tested against a local fixture server (not actual model inference).

Tests verify policy acceptance, targeted repair payload, two-repair exhaustion, unchanged/oscillating outputs, initial generation, missing worker, uncertainty, confidence, hard gates over aggregate score, missing evidence, deterministic JSON validation, malformed responses/distributions, input/threshold validation, missing key, conservative context guard, command adapter, 429 retry and bearer header, redirect refusal, local-only Ollama origin, worker failure and metadata-only logs.

## Current test count

110 tests across 6 files. Run without credentials:

```bash
python -m pytest tests/
# or
python -m unittest discover -s tests -v
```

## Not executed (V1)

- Authenticated TypeSafe/Jev call: credentials absent.
- AI generation/repair using a real local or remote model: worker absent.
- Quality benchmark or calibrated threshold tuning: deliberately outside V1 build scope.
- User-account balance, credit origin or custom quota verification: account unavailable.

Offline PASS is a control-flow test result, not proof that real Jev will accept the example. A live result may legitimately be HUMAN REVIEW. Use the README live commands with your actual key and worker to complete live validation.

## Benchmark execution

The canonical 36-case Noul Benchmark v1.0 validates the full evaluation engine against labelled ACCEPT / REPAIR / HUMAN_REVIEW cases. Requires `TYPESAFE_API_KEY` in `.env`.

```bash
# Validate fixture integrity only (offline, no credentials):
python benchmarks/validate_fixture.py

# Run full benchmark (live provider calls; uses cache if present):
python benchmarks/run_benchmark.py
```

### Cache behaviour

`benchmarks/run_benchmark.py` caches provider responses in `benchmarks/.api_cache.json` (gitignored). On subsequent runs, cached cases are replayed from disk without contacting the TypeSafe API. The console output shows noul/confidence values from cached responses; it does **not** indicate whether each case was live or cached.

To distinguish cached from live: cases present in `.api_cache.json` at the start of a run are replayed; cases absent trigger live provider calls. The cache is keyed by `case_id`.

To force a fully fresh live run (all 36 cases hit the API):

```powershell
# PowerShell
Remove-Item benchmarks\.api_cache.json -ErrorAction SilentlyContinue
python benchmarks/run_benchmark.py
```

```bash
# bash
rm -f benchmarks/.api_cache.json
python benchmarks/run_benchmark.py
```

Results are saved to `benchmarks/baseline_results.json` (gitignored).
