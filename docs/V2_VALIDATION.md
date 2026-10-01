# V2 validation — 2026-10-01

- **45/45 automated tests passed:** 26 V1 regressions unchanged; 19 V2 tests.
- `python examples/demo_v2.py`: local HTTP fixture plus subprocess worker; detects FR002/FR005/FR009, REVISE → one targeted repair → PASS; clean candidate PASS, zero repairs. Request sizes 15 / 16 / 15 questions.
- `python examples/demo.py`: original V1 offline demo still passes (REVISE → PASS, one repair, two evaluations).
- `python run.py --help`: new repeatable `--rules` and `--no-rules` flags available.
- `--no-rules`/Python rules omitted retains the original V1 evaluation questions and state, verified by regression tests.
- Jev client, worker, universal profile, thresholds and original Master Handoff unchanged from the V1 archive.

V2 tests additionally verify: critical rule blocking Score=4/Choice=none; INFO does not rewrite; uncertainty review; disabled/task-scoped rules; repeated-rule logging and two-repair cap; FR007 requires baseline and passes restoration reference; deterministic JSON fields skip Jev; packs extend configuration without core changes; duplicate/malformed rule/reuse criteria rejection; missing extra answers fail safely; base HUMAN REVIEW cannot be downgraded.

**Not verified live:** Actual Jev detection/accuracy, real model repair, account-specific credits. No credentials or actual worker are configured. Offline fixture detections are not represented as live results. No extra paid service, domain pack, benchmark dataset or V3 work was added.

## Minimal delta

Added: `rules/universal.json`, `src/jev_engine/failure_rules.py`, `tests/test_failure_rules.py`, `examples/demo_v2.py`, `docs/FAILURE_RULES.md`, `docs/V2_VALIDATION.md`, `docs/demo-v2-result.json`.

Modified: `src/jev_engine/engine.py`, `policy.py`, `repair.py`, `normalize.py`, `__main__.py`, and `README.md`.

The original V1 archive remains available unchanged. The V2 archive contains the full runnable project for convenience, rather than requiring manual patching.
