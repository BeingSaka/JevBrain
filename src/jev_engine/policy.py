from .normalize import EngineError
from .jev_client import number

POSITIVE = ("requirements_met", "evidence_sufficient", "ready_to_deliver")
NEGATIVE = ("critical_requirement_missing", "instruction_violation_present",
            "internal_contradiction_present", "unsupported_claim_present")

def validate_thresholds(t):
    expected = {"accept_min", "risk_max", "failure_min", "score_min", "confidence_min"}
    allowed = expected | {"semantic_evaluation_enabled"}
    if not isinstance(t, dict) or not expected.issubset(set(t)) or (set(t) - allowed):
        raise EngineError("Invalid threshold config")
    for k in expected: number(t[k], 0, 4 if k == "score_min" else 1)
    if not t["risk_max"] < t["failure_min"] or not 1-t["accept_min"] < t["failure_min"]:
        raise EngineError("Thresholds need an uncertainty band")
    return t

def _base_decision(response, t):
    a = response["answers"]
    failed = [k for k in POSITIVE if a[k]["noul"] < t["accept_min"]]
    failed += [k for k in NEGATIVE if a[k]["noul"] > t["risk_max"]]
    c, s = a["primary_failure"], a["production_readiness"]
    if s["score"] < t["score_min"]: failed.append("production_readiness")
    if c["choice"] != "none": failed.append("primary_failure")
    if min(c["confidence"], s["confidence"]) < t["confidence_min"]:
        return "HUMAN REVIEW", failed, "Low Choice/Score confidence"
    if not failed: return "PASS", [], "All configured gates passed"
    clear = all(1-a[k]["noul"] >= t["failure_min"] for k in failed if k in POSITIVE)
    clear &= all(a[k]["noul"] >= t["failure_min"] for k in failed if k in NEGATIVE)
    if not clear: return "HUMAN REVIEW", failed, "Noul judgment in uncertainty band"
    if "evidence_sufficient" in failed or c["choice"] in ("insufficient_evidence", "other"):
        return "HUMAN REVIEW", failed, "Evidence or correction is unresolved"
    if c["choice"] == "none":
        return "HUMAN REVIEW", failed, "Failed gates without an actionable failure class"
    return "REVISE", failed, "Confident actionable failure"


def decide(response, t, rule_findings=None):
    decision, failed, reason = _base_decision(response, t)
    blocking = [r for r in (rule_findings or []) if r["severity"] != "INFO" and r["status"] != "clear"]
    if not blocking: return decision, failed, reason
    failed = failed + ["rule:"+r["rule_id"] for r in blocking]
    if decision == "HUMAN REVIEW": return decision, failed, reason
    if any(r["status"] == "uncertain" for r in blocking):
        return "HUMAN REVIEW", failed, "Failure-rule probability in uncertainty band"
    # A concrete triggered rule supplies actionable feedback even if Choice says none.
    return "REVISE", failed, "Triggered blocking failure rules"
