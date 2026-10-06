import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from jev_engine.__main__ import get_parser, load_env
from jev_engine.engine import Engine
from jev_engine.failure_rules import load_packs
from jev_engine.jev_client import JevClient
from jev_engine.logging import JsonlLogger
from jev_engine.normalize import EngineError, normalize
from jev_engine.worker import configured_worker

MAX_FIELD_BYTES = 200 * 1024
JOB_DURATION_SCOPE = (
    "includes payload normalization and validation, engine construction/setup, "
    "Engine.run, and all repair attempts; excludes response serialization"
)


def parse_cli_args(argv=None):
    return get_parser().parse_args(["app-local-input.json", *(argv or [])])


def build_engine(args=None):
    args = args or parse_cli_args()
    if args.env_file:
        load_env(args.env_file)

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    if profile.get("name") != "universal":
        raise EngineError("Only the universal profile ships in this release")

    if args.no_rules and args.rules:
        raise EngineError("Choose --rules or --no-rules")
    rules = [] if args.no_rules else load_packs(args.rules or ["rules/universal.json"], profile)
    thresholds = json.loads(Path(args.thresholds).read_text())
    logger = JsonlLogger(args.log)
    worker = configured_worker()
    return Engine(
        JevClient(),
        worker,
        profile,
        thresholds,
        logger,
        rules=rules,
        semantic_evaluation_enabled=args.semantic,
    )


def _validate_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if len(value.encode("utf-8")) > MAX_FIELD_BYTES:
        raise ValueError(f"{field_name} exceeds 200 KB")
    return value


def _validate_lines(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines()]
        lines = [line for line in lines if line]
    elif isinstance(value, list):
        lines = []
        for part in value:
            if not isinstance(part, str):
                raise ValueError(f"{field_name} must be a list of strings")
            cleaned = part.strip()
            if cleaned:
                lines.append(cleaned)
    else:
        raise ValueError(f"{field_name} must be a list of strings or a newline-delimited string")

    for line in lines:
        if len(line.encode("utf-8")) > MAX_FIELD_BYTES:
            raise ValueError(f"{field_name} contains a value over 200 KB")
    return lines


def _normalize_payload(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Request body must be a JSON object")

    if "original_request" not in raw:
        raise ValueError("missing original_request")
    state: Dict[str, Any] = {
        "original_request": _validate_text(raw["original_request"], "original_request"),
        "locked_requirements": _validate_lines(raw.get("locked_requirements", []), "locked_requirements"),
        "output_type": "text",
        "available_evidence": "",
        "known_constraints": [],
        "candidate_output": None,
    }

    if "candidate_output" in raw:
        state["candidate_output"] = _validate_text(raw["candidate_output"], "candidate_output")
    if "output_type" in raw:
        state["output_type"] = _validate_text(raw["output_type"], "output_type")
    if "available_evidence" in raw:
        state["available_evidence"] = _validate_text(raw["available_evidence"], "available_evidence")
    if "known_constraints" in raw:
        state["known_constraints"] = _validate_lines(raw["known_constraints"], "known_constraints")
    if "deterministic_checks" in raw:
        checks = raw["deterministic_checks"]
        if not isinstance(checks, dict):
            raise ValueError("deterministic_checks must be an object")
        state["deterministic_checks"] = checks

    if not state["locked_requirements"]:
        raise ValueError("locked_requirements must contain at least one requirement")
    if state["candidate_output"] is not None and not state["candidate_output"].strip():
        raise ValueError("candidate_output must not be empty")

    try:
        normalize(state)
    except EngineError:
        raise ValueError("Invalid evaluation request") from None

    return state


def _provider_failure(result: Any):
    if not isinstance(result, dict):
        return None
    history = result.get("history")
    if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
        return None
    reason = history[-1].get("reason")
    if reason == "TYPESAFE_API_KEY is not configured":
        return "provider_config"
    if isinstance(reason, str) and reason.startswith((
        "Provider HTTP ",
        "Provider connection/timeout failure",
        "Provider returned invalid JSON",
        "Provider response exceeds size limit",
        "Provider requests a later retry",
    )):
        return "provider"
    return None


def _error(error_type: str) -> Dict[str, Any]:
    messages = {
        "validation": "Invalid evaluation request.",
        "provider_config": "Evaluation provider is not configured.",
        "provider": "Evaluation provider is unavailable.",
        "engine": "Engine evaluation failed.",
    }
    return {"ok": False, "error": {"type": error_type, "message": messages[error_type]}}


def evaluate(payload: Any, args=None) -> Dict[str, Any]:
    started = time.perf_counter_ns()
    try:
        state = _normalize_payload(payload)
    except (TypeError, ValueError):
        return _error("validation")

    try:
        engine = build_engine(args)
    except Exception:
        return _error("engine")

    try:
        result = engine.run(state)
    except Exception:
        return _error("engine")

    duration_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    provider_error = _provider_failure(result)
    if provider_error:
        return _error(provider_error)
    return {
        "ok": True,
        "result": result,
        "job_duration_ms": float(duration_ms),
        "job_duration_scope": JOB_DURATION_SCOPE,
    }
