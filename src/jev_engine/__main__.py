import argparse
import json
import os
import sys
from pathlib import Path
from .engine import Engine
from .jev_client import JevClient
from .logging import JsonlLogger
from .normalize import EngineError
from .worker import configured_worker
from .failure_rules import load_packs

def load_env(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        key, sep, value = line.partition("=")
        if not sep or not key.replace("_", "").isalnum(): raise EngineError("Invalid env file")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'): value = value[1:-1]
        os.environ.setdefault(key, value)

def get_parser():
    parser = argparse.ArgumentParser(description="Jev Universal Evaluation & Decision Engine")
    parser.add_argument("input", help="JSON input path")
    parser.add_argument("--env-file")
    parser.add_argument("--output")
    parser.add_argument("--log", default="logs/evaluations.jsonl")
    parser.add_argument("--profile", default="evaluators/universal.json")
    parser.add_argument("--thresholds", default="config/thresholds.json")
    parser.add_argument("--rules", action="append", help="Rule pack JSON; repeat to combine packs")
    parser.add_argument("--no-rules", action="store_true", help="Run unchanged V1 evaluation without failure rules")
    parser.add_argument("--semantic", action=argparse.BooleanOptionalAction, default=True, help="Enable/disable Noul + Choice + Score semantic evaluation pipeline (default: enabled)")
    return parser

def main(argv=None):
    parser = get_parser()
    args = parser.parse_args(argv)
    try:
        if args.env_file: load_env(args.env_file)
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        if profile.get("name") != "universal": raise EngineError("Only the universal profile ships in this release")
        if args.no_rules and args.rules: raise EngineError("Choose --rules or --no-rules")
        rules = [] if args.no_rules else load_packs(args.rules or ["rules/universal.json"], profile)
        engine = Engine(JevClient(), configured_worker(), profile,
            json.loads(Path(args.thresholds).read_text()), JsonlLogger(args.log), rules=rules,
            semantic_evaluation_enabled=args.semantic)
        result = engine.run(json.loads(Path(args.input).read_text(encoding="utf-8")))
        text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
        if args.output: Path(args.output).write_text(text+"\n", encoding="utf-8")
        print(text)
        return 0 if result["decision"] == "PASS" else 2
    except (EngineError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"decision":"HUMAN REVIEW", "reason":"Invalid input/configuration or unavailable file; no provider body or secrets printed"}), file=sys.stderr)
        return 2

if __name__ == "__main__": sys.exit(main())
