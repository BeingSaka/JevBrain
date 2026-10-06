"""Non-authoritative V2 shadow decision scaffold; no provider or V1-engine calls."""

import hashlib
import json
from pathlib import Path


V2_PASS = "V2_PASS"
V2_REPAIR = "V2_REPAIR"
V2_HUMAN_REVIEW = "V2_HUMAN_REVIEW"
V2_INSUFFICIENT_EVIDENCE = "V2_INSUFFICIENT_EVIDENCE"
AUTHORITY_NOTE = "V1 remains authoritative; V2 is observational only."
_RULE_IDS = {f"FR{i:03d}" for i in range(1, 11)}
_CRITICAL = {"FR001", "FR002", "FR003", "FR004", "FR006", "FR007", "FR008", "FR009"}
_STATUSES = {"CLEAR_VIOLATION", "CLEAR_NON_VIOLATION", "AMBIGUOUS", "UNAVAILABLE"}
_EVIDENCE = {"SUFFICIENT", "MISSING", "CONFLICTING", "UNAVAILABLE"}
_FORMAT_CHECKS = {"required_substrings", "forbidden_substrings", "max_chars", "valid_json", "json_required_fields"}


def _canonical_sha256(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_rules(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else None
    if data.get("shadow_version") != "2.0.0-shadow" or not isinstance(rules, list):
        raise ValueError("Invalid V2 shadow rule pack")
    ids = [rule.get("rule_id") for rule in rules if isinstance(rule, dict)]
    if set(ids) != _RULE_IDS or len(ids) != len(set(ids)):
        raise ValueError("V2 shadow rules must declare FR001 through FR010 exactly once")
    for rule in rules:
        if set(rule) != {"rule_id", "v2_class", "relevance_gate"}:
            raise ValueError("Invalid V2 shadow rule schema")
        if not all(isinstance(rule[key], str) and rule[key] for key in rule):
            raise ValueError("V2 shadow rule values must be nonempty strings")
    return rules


def _has_format_contract(state):
    checks = state.get("deterministic_checks", {})
    return isinstance(checks, dict) and bool(_FORMAT_CHECKS & set(checks))


def _verbatim_preservation_requested(state):
    checks = state.get("deterministic_checks", {})
    return isinstance(checks, dict) and checks.get("preserve_previous_candidate_verbatim") is True


def _fr007_verbatim_violation(state):
    if not _verbatim_preservation_requested(state):
        return None
    previous = state.get("previous_candidate")
    candidate = state.get("candidate_output")
    if not isinstance(previous, str) or not previous or not isinstance(candidate, str) or not candidate:
        return None
    if previous in candidate:
        return None
    return {
        "gate_id": "FR007_verbatim_preservation",
        "status": "FAIL",
        "actionable": True,
        "evidence": "FR007 CLEAR_VIOLATION: previous_candidate is not preserved exactly in candidate_output.",
    }


def route_rules(state, rules, deterministically_resolved=(), deterministically_violated=()):
    if not isinstance(state, dict):
        raise ValueError("Shadow state must be an object")
    resolved = set(deterministically_resolved)
    if resolved - {"FR006"}:
        raise ValueError("Only FR006 may be structurally resolved by deterministic checks")
    violated = set(deterministically_violated)
    if violated - {"FR007"}:
        raise ValueError("Only FR007 may be structurally violated by deterministic checks")
    considered, skipped, relevance = [], [], []
    locks_present = bool(state.get("locked_requirements") or state.get("known_constraints"))
    for rule in rules:
        rule_id, gate = rule["rule_id"], rule["relevance_gate"]
        if rule_id == "FR007" and rule_id in violated:
            skipped.append({"rule_id": rule_id, "reason": "verbatim_preservation_failed_deterministically"})
            relevance.append({"rule_id": rule_id, "status": "RESOLVED_DETERMINISTICALLY"})
        elif rule_id == "FR006" and rule_id in resolved:
            skipped.append({"rule_id": rule_id, "reason": "format_contract_resolved_deterministically"})
            relevance.append({"rule_id": rule_id, "status": "IRRELEVANT_PROVEN"})
        elif gate == "previous_candidate" and not state.get("previous_candidate") and not _verbatim_preservation_requested(state):
            skipped.append({"rule_id": rule_id, "reason": "previous_candidate_absent"})
            relevance.append({"rule_id": rule_id, "status": "IRRELEVANT_PROVEN"})
        elif gate == "format_contract" and not _has_format_contract(state):
            skipped.append({"rule_id": rule_id, "reason": "format_contract_absent"})
            relevance.append({"rule_id": rule_id, "status": "IRRELEVANT_PROVEN"})
        else:
            considered.append(rule_id)
            status = "RELEVANT" if gate == "lock_context" and locks_present else "UNCERTAIN"
            relevance.append({"rule_id": rule_id, "status": status})
    return {"considered_rules": considered, "skipped_rules": skipped, "relevance": relevance}


def _normalise_criteria(criteria, considered):
    if not isinstance(criteria, list):
        criteria = []
    indexed, invalid = {}, False
    for item in criteria:
        if not isinstance(item, dict) or item.get("rule_id") not in _RULE_IDS:
            invalid = True
            continue
        rule_id = item["rule_id"]
        status = item.get("status")
        evidence_status = item.get("evidence_status", "SUFFICIENT")
        if status not in _STATUSES or evidence_status not in _EVIDENCE:
            indexed[rule_id] = {"rule_id": rule_id, "status": "UNAVAILABLE", "evidence_status": "UNAVAILABLE", "actionable": False, "evidence": "Invalid injected criterion result."}
            invalid = True
            continue
        indexed[rule_id] = {
            "rule_id": rule_id,
            "status": status,
            "evidence_status": evidence_status,
            "actionable": bool(item.get("actionable", False)),
            "evidence": item.get("evidence", ""),
        }
    for rule_id in considered:
        if rule_id in _CRITICAL and rule_id not in indexed:
            indexed[rule_id] = {"rule_id": rule_id, "status": "UNAVAILABLE", "evidence_status": "UNAVAILABLE", "actionable": False, "evidence": "No injected criterion result."}
    return [indexed[key] for key in sorted(indexed)], invalid


def _deterministic_outcome(gates):
    for gate in gates:
        if gate["status"] == "FAIL":
            return V2_REPAIR if gate["actionable"] else V2_HUMAN_REVIEW, gate["gate_id"]
    return None, None


def plan_shadow_evaluation(state, rules, deterministic_gates=(), deterministically_resolved=()):
    fr007_gate = _fr007_verbatim_violation(state)
    routing = route_rules(state, rules, deterministically_resolved, ("FR007",) if fr007_gate else ())
    gates = ([fr007_gate] if fr007_gate else []) + list(deterministic_gates)
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != {"gate_id", "status", "actionable", "evidence"} or gate["status"] not in {"PASS", "FAIL", "NOT_APPLICABLE"}:
            raise ValueError("Invalid deterministic gate")
    criteria = []
    if fr007_gate:
        criteria.append({"rule_id": "FR007", "status": "CLEAR_VIOLATION", "evidence_status": "SUFFICIENT", "actionable": True, "evidence": fr007_gate["evidence"]})
    return {"routing": routing, "deterministic_gates": gates, "criterion_results": criteria}


def _outcome(criteria, considered, trusted_synthetic_fixture, invalid):
    if invalid:
        return V2_HUMAN_REVIEW, "Invalid injected criterion result."
    critical = [item for item in criteria if item["rule_id"] in _CRITICAL and item["rule_id"] in considered]
    if any(item["evidence_status"] in {"MISSING", "CONFLICTING"} for item in critical):
        return V2_INSUFFICIENT_EVIDENCE, "Relevant critical criterion lacks resolved evidence."
    if any(item["status"] == "AMBIGUOUS" for item in critical):
        return V2_HUMAN_REVIEW, "Relevant critical criterion is ambiguous."
    violation = next((item for item in critical if item["status"] == "CLEAR_VIOLATION"), None)
    if violation:
        return (V2_REPAIR if violation["actionable"] else V2_HUMAN_REVIEW), f"Clear critical violation: {violation['rule_id']}."
    if any(item["status"] == "UNAVAILABLE" for item in critical):
        return V2_HUMAN_REVIEW, "Relevant critical criterion is unavailable."
    if trusted_synthetic_fixture:
        return V2_PASS, "Trusted synthetic fixture has clear non-violations for all relevant critical criteria."
    return V2_HUMAN_REVIEW, "Calibration is unavailable; V2 cannot authorize PASS."


def validate_audit(record):
    required = {"shadow_version", "input_sha256", "v1_authority", "deterministic_gates", "routing", "criterion_results", "ambiguous_criteria", "diagnostic_readiness_signals", "v2_result", "v2_reason", "authority_note"}
    if not isinstance(record, dict) or set(record) != required:
        raise ValueError("Invalid V2 shadow audit schema")
    if record["shadow_version"] != "2.0.0-shadow" or record["authority_note"] != AUTHORITY_NOTE:
        raise ValueError("Invalid V2 shadow audit identity")
    if record["v2_result"] not in {V2_PASS, V2_REPAIR, V2_HUMAN_REVIEW, V2_INSUFFICIENT_EVIDENCE}:
        raise ValueError("Invalid V2 shadow result")
    routing = record["routing"]
    if set(routing) != {"considered_rules", "skipped_rules", "relevance"}:
        raise ValueError("Invalid V2 routing audit")
    accounted = set(routing["considered_rules"]) | {item["rule_id"] for item in routing["skipped_rules"]}
    if accounted != _RULE_IDS:
        raise ValueError("Every V2 rule must be considered or skipped")
    return record


def evaluate_shadow(state, v1_authority, rules, criterion_results, deterministic_gates=(), diagnostic_readiness_signals=None, trusted_synthetic_fixture=False, deterministically_resolved=()):
    if not isinstance(v1_authority, dict) or set(v1_authority) != {"decision", "reason"}:
        raise ValueError("V1 authority record must contain decision and reason")
    plan = plan_shadow_evaluation(state, rules, deterministic_gates, deterministically_resolved)
    routing, gates = plan["routing"], plan["deterministic_gates"]
    criteria_input = list(criterion_results) if isinstance(criterion_results, list) else []
    for deterministic in plan["criterion_results"]:
        criteria_input = [item for item in criteria_input if not isinstance(item, dict) or item.get("rule_id") != deterministic["rule_id"]]
        criteria_input.append(deterministic)
    criteria, invalid = _normalise_criteria(criteria_input, set(routing["considered_rules"]))
    result, reason = _deterministic_outcome(gates)
    if result is None:
        result, reason = _outcome(criteria, set(routing["considered_rules"]), trusted_synthetic_fixture, invalid)
    record = {
        "shadow_version": "2.0.0-shadow",
        "input_sha256": _canonical_sha256(state),
        "v1_authority": dict(v1_authority),
        "deterministic_gates": gates,
        "routing": routing,
        "criterion_results": criteria,
        "ambiguous_criteria": [item["rule_id"] for item in criteria if item["status"] == "AMBIGUOUS"],
        "diagnostic_readiness_signals": dict(diagnostic_readiness_signals or {}),
        "v2_result": result,
        "v2_reason": reason,
        "authority_note": AUTHORITY_NOTE,
    }
    return validate_audit(record)
