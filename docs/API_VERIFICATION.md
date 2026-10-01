# Official API verification — 2026-10-01

Primary sources were read in full where relevant. Search surfaced numerous independent Jev sites with different endpoints, keys, billing and limits; they were not treated as TypeSafe authority or integrated.

| Requirement | Verified surface | Implementation |
|---|---|---|
| Direct API | POST https://api.typesafe.ai/v1/systemone; Bearer TypeSafe key; model/state/questions | Standard-library HTTP; TYPESAFE_API_KEY; pin jev-1.13.0 |
| Structured state | String/object/array | Validated structured object |
| Noul | Probability 0–1; optional true/false criteria | Seven explicit checks with both criteria |
| Choice | Criteria map; ≤255 options; choice/probabilities/confidence | Nine failure categories |
| Score | Ordered 2–10 levels; weighted score, legend, probabilities, confidence | Five levels (0–4) |
| Compatible batching | Mixed questions, parallel and isolated against shared state | All nine questions in one call |
| Routing authority | Structured outputs consumed by code | Local configurable policy |
| Generation | Jev does not generate text | Separate local Ollama or existing command worker |
| HTTP errors | 401, 422, 429, 529; backoff advised for 429/529 | Safe errors; bounded retry; review on failure |
| Usage | input_tokens/output_tokens | JSONL usage and estimated cost |
| Model/version | jev-1.13.0; latest/preview currently alias same version | Stable pinned version with env override |
| Price | $42/Btok = $0.042/Mtok input; output free | Local cost estimate, not provider invoice |
| Context | 64K total; 32K state + longest question | Conservative byte guard; no truncation |
| Rate limits | 100K tokens/sec, 40 requests/sec, dynamically adjustable | Sequential V1 calls plus bounded rate-limit handling |

**Compatibility verdict:** No fundamental incompatibility with the approved V1. HTTP avoids SDK installation and does not alter the architecture. The official Python SDK is `typesafe-sdk`, import `typesafe_sdk`, with synchronous/asynchronous clients; JavaScript SDK is `@typesafe-ai/sdk`. The official Python repository is MIT licensed. Neither SDK is required by this implementation.

**Account-dependent UNKNOWN:** Whether the user's credits belong to direct TypeSafe or an independent gateway; account balance, free allocation, customized quotas and actual key permissions. Those cannot be verified from public documentation or without credentials. Do not substitute a gateway or enter a key into a similarly named third-party site.

**Live validation status:** No TYPESAFE_API_KEY, OLLAMA_MODEL or WORKER_COMMAND_JSON was present. No paid evaluation or credentialed request was made. HTTP contract fixtures were used for integration tests; live response compatibility remains to be exercised by the supplied run commands.

## Sources

- Introduction: https://docs.typesafe.ai/introduction
- Full API contract: https://docs.typesafe.ai/api
- Models, price, limits, language/input support: https://docs.typesafe.ai/models
- Python SDK: https://docs.typesafe.ai/sdk/python
- Official Python source: https://github.com/typesafe-ai/typesafe-sdk-python
- SDKs: https://docs.typesafe.ai/sdk
- Key setup/quickstart: https://docs.typesafe.ai/introduction/quickstart
- Known model failures: https://docs.typesafe.ai/model-jaggedness/jev-1.13
- Local generation worker: https://docs.ollama.com/api/generate

Known Jev limitations relevant to V1: literal interpretation, unreliable counting/numeric precision/date arithmetic, indirection and long irrelevant state, adversarial content, and nonguaranteed consistency between independent questions. Therefore exact checks belong in code, evidence is explicit, no question reads another question's answer, and probabilities are never treated as proof.
