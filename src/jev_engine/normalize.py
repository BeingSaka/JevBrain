import json

class EngineError(Exception):
    """Safe error message suitable for logs; never include provider response bodies."""

FIELDS = {"original_request", "locked_requirements", "candidate_output", "output_type",
          "available_evidence", "known_constraints", "deterministic_checks", "previous_candidate", "allowed_changes"}

def normalize(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise EngineError("Input must be an object with documented fields only")
    state = {"original_request": data.get("original_request"),
             "candidate_output": data.get("candidate_output"),
             "output_type": data.get("output_type", "text"),
             "available_evidence": data.get("available_evidence", ""),
             "locked_requirements": data.get("locked_requirements", []),
             "known_constraints": data.get("known_constraints", [])}
    for k in ("original_request", "output_type", "available_evidence"):
        if not isinstance(state[k], str) or (k != "available_evidence" and not state[k].strip()):
            raise EngineError(f"{k} must be a nonempty string (evidence may be empty)")
    if state["candidate_output"] is not None and not isinstance(state["candidate_output"], str):
        raise EngineError("candidate_output must be a string or null")
    for k in ("locked_requirements", "known_constraints"):
        if not isinstance(state[k], list) or any(not isinstance(x, str) or not x.strip() for x in state[k]):
            raise EngineError(f"{k} must be a list of nonempty strings")
    if "previous_candidate" in data:
        if not isinstance(data["previous_candidate"],str) or not data["previous_candidate"].strip():
            raise EngineError("previous_candidate must be a nonempty string")
        state["previous_candidate"] = data["previous_candidate"]
    if "allowed_changes" in data:
        if not isinstance(data["allowed_changes"],list) or any(not isinstance(x,str) or not x.strip() for x in data["allowed_changes"]):
            raise EngineError("allowed_changes must be a list of nonempty strings")
        state["allowed_changes"] = data["allowed_changes"]
    checks = data.get("deterministic_checks", {})
    allowed = {"required_substrings", "forbidden_substrings", "max_chars", "valid_json", "json_required_fields"}
    if not isinstance(checks, dict) or set(checks) - allowed:
        raise EngineError("Unknown deterministic check")
    for k in ("required_substrings", "forbidden_substrings", "json_required_fields"):
        if k in checks and (not isinstance(checks[k], list) or any(not isinstance(x, str) or not x for x in checks[k])):
            raise EngineError(f"Invalid {k}")
    if "max_chars" in checks and (type(checks["max_chars"]) is not int or checks["max_chars"] < 1):
        raise EngineError("max_chars must be a positive integer")
    if "valid_json" in checks and type(checks["valid_json"]) is not bool:
        raise EngineError("valid_json must be boolean")
    return state, checks

def deterministic(candidate, checks):
    failures = []
    if not candidate.strip(): failures.append("candidate_empty")
    if any(x not in candidate for x in checks.get("required_substrings", [])):
        failures.append("required_substrings")
    if any(x in candidate for x in checks.get("forbidden_substrings", [])):
        failures.append("forbidden_substrings")
    if len(candidate) > checks.get("max_chars", float("inf")): failures.append("max_chars")
    if checks.get("valid_json") or "json_required_fields" in checks:
        try: parsed = json.loads(candidate, parse_constant=lambda x: (_ for _ in ()).throw(ValueError()))
        except (ValueError, TypeError):
            failures.append("valid_json")
            if "json_required_fields" in checks: failures.append("json_required_fields")
        else:
            if "json_required_fields" in checks and (not isinstance(parsed,dict) or any(k not in parsed for k in checks["json_required_fields"])):
                failures.append("json_required_fields")
    return failures
