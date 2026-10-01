# V1 validation — 2026-10-01

## Executed

- `python -m unittest discover -s tests -v`: **26/26 passed**.
- `python examples/demo.py`: local HTTP contract fixture + subprocess worker fixture → REVISE → PASS; exactly one repair and two evaluations. `demo-result.json` contains the summary.
- `python run.py examples/input.json --output /tmp/jev-no-key-result.json`: **HUMAN REVIEW**, `TYPESAFE_API_KEY is not configured`, zero repairs, CLI exit 2; logged safely without credentials.
- TypeSafe payload/response schema checked against current official API reference.
- Local Ollama HTTP adapter tested against a local fixture server (not actual model inference).

Tests verify policy acceptance, targeted repair payload, two-repair exhaustion, unchanged/oscillating outputs, initial generation, missing worker, uncertainty, confidence, hard gates over aggregate score, missing evidence, deterministic JSON validation, malformed responses/distributions, input/threshold validation, missing key, conservative context guard, command adapter, 429 retry and bearer header, redirect refusal, local-only Ollama origin, worker failure and metadata-only logs.

## Not executed

- Authenticated TypeSafe/Jev call: credentials absent.
- AI generation/repair using a real local or remote model: worker absent.
- Quality benchmark or calibrated threshold tuning: deliberately outside V1 build scope.
- User-account balance, credit origin or custom quota verification: account unavailable.

Offline PASS is a control-flow test result, not proof that real Jev will accept the example. A live result may legitimately be HUMAN REVIEW. Use the README live commands with your actual key and worker to complete live validation.
