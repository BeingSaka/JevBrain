"""Explicit offline V2 shadow runner; it has no provider or V1-engine integration."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jev_engine.v2_shadow import evaluate_shadow, load_rules
from jev_engine.v2_criterion_evaluator import evaluate_with_criterion_evaluator, load_criterion_profile


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None, evaluator_factory=None):
    parser = argparse.ArgumentParser(description="Run the non-authoritative V2 shadow scaffold with injected criteria.")
    parser.add_argument("--input", required=True, help="Normalized shadow state JSON.")
    parser.add_argument("--criteria", help="Injected criterion-results JSON array.")
    parser.add_argument("--live-semantic", action="store_true", help="Reserved explicit boundary; live semantic execution is not enabled.")
    parser.add_argument("--v1-authority", required=True, help="Existing V1 decision/reason JSON object.")
    parser.add_argument("--output", required=True, help="Explicit audit-record output path.")
    parser.add_argument("--rules", default=str(ROOT / "rules" / "v2_shadow.json"))
    parser.add_argument("--profile", default=str(ROOT / "evaluators" / "v2_shadow.json"))
    args = parser.parse_args(argv)
    if args.live_semantic:
        if evaluator_factory is None:
            from jev_engine.jev_client import JevClient
            evaluator_factory = JevClient
        record = evaluate_with_criterion_evaluator(
            read_json(args.input), read_json(args.v1_authority), load_rules(args.rules),
            load_criterion_profile(args.profile), evaluator=evaluator_factory(),
        )
    else:
        if not args.criteria:
            parser.error("--criteria is required for offline execution.")
        record = evaluate_shadow(read_json(args.input), read_json(args.v1_authority), load_rules(args.rules), read_json(args.criteria))
    Path(args.output).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
