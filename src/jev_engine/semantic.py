"""Semantic evaluation dimensions (Noul, Choice, Score) for JEV evaluation engine."""
import math
from .normalize import EngineError
from .jev_client import number

CHOICE_ENUM = {
    "none",
    "missing_requirement",
    "instruction_violation",
    "contradiction",
    "unsupported_claim",
    "insufficient_evidence",
    "generic_output",
    "format_violation",
    "other",
}

POSITIVE_NOULS = ("requirements_met", "evidence_sufficient", "ready_to_deliver")
NEGATIVE_NOULS = (
    "critical_requirement_missing",
    "instruction_violation_present",
    "internal_contradiction_present",
    "unsupported_claim_present",
)

def validate_semantic_evaluation(data):
    """Strictly validates the semantic evaluation output contract (Specification v1 Section 11)."""
    if not isinstance(data, dict):
        raise EngineError("Semantic evaluation must be a JSON object")
    
    required_keys = {"noul", "choice", "score", "concerns", "repair_targets"}
    if not required_keys.issubset(set(data)):
        raise EngineError(f"Semantic evaluation missing required fields: {required_keys - set(data)}")
    
    # Noul validation: value (0.0-1.0), confidence (0.0-1.0)
    noul = data["noul"]
    if not isinstance(noul, dict) or "value" not in noul or "confidence" not in noul:
        raise EngineError("noul must be an object with value and confidence")
    number(noul["value"], 0.0, 1.0)
    number(noul["confidence"], 0.0, 1.0)
    if "reason" in noul and not isinstance(noul["reason"], str):
        raise EngineError("noul.reason must be a string")

    # Choice validation: value in enum, confidence (0.0-1.0)
    choice = data["choice"]
    if not isinstance(choice, dict) or "value" not in choice or "confidence" not in choice:
        raise EngineError("choice must be an object with value and confidence")
    if choice["value"] not in CHOICE_ENUM:
        raise EngineError(f"choice.value must be one of {sorted(CHOICE_ENUM)}, got: {choice['value']}")
    number(choice["confidence"], 0.0, 1.0)
    if "reason" in choice and not isinstance(choice["reason"], str):
        raise EngineError("choice.reason must be a string")

    # Score validation: value (0.0-4.0), confidence (0.0-1.0)
    score = data["score"]
    if not isinstance(score, dict) or "value" not in score or "confidence" not in score:
        raise EngineError("score must be an object with value and confidence")
    number(score["value"], 0.0, 4.0)
    number(score["confidence"], 0.0, 1.0)
    if "reason" in score and not isinstance(score["reason"], str):
        raise EngineError("score.reason must be a string")

    # Optional evidence_resolvable validation: value (0.0-1.0), confidence (0.0-1.0)
    if "evidence_resolvable" in data:
        er = data["evidence_resolvable"]
        if not isinstance(er, dict) or "value" not in er or "confidence" not in er:
            raise EngineError("evidence_resolvable must be an object with value and confidence")
        number(er["value"], 0.0, 1.0)
        number(er["confidence"], 0.0, 1.0)
        if "reason" in er and not isinstance(er["reason"], str):
            raise EngineError("evidence_resolvable.reason must be a string")

    # Concerns validation: list of strings
    if not isinstance(data["concerns"], list) or any(not isinstance(x, str) for x in data["concerns"]):
        raise EngineError("concerns must be a list of strings")

    # Repair targets validation: list of objects with type, location, instruction
    targets = data["repair_targets"]
    if not isinstance(targets, list):
        raise EngineError("repair_targets must be a list")
    for t in targets:
        if not isinstance(t, dict) or not {"type", "location", "instruction"}.issubset(set(t)):
            raise EngineError("Each repair target must contain type, location, and instruction")
        for k in ("type", "location", "instruction"):
            if not isinstance(t[k], str) or not t[k].strip():
                raise EngineError(f"repair_target.{k} must be a nonempty string")

    return data


def extract_semantic_evaluation(raw_response, state, checks, rule_findings=None):
    """
    Extracts and normalizes the unified SemanticEvaluation schema from the single
    batched Jev evaluation response.
    """
    if not isinstance(raw_response, dict):
        raise EngineError("Evaluator response must be a dictionary")

    answers = raw_response.get("answers")
    if not isinstance(answers, dict):
        raise EngineError("Missing answers dictionary in evaluation response")

    # 1. Extract Choice (primary failure)
    choice_raw = answers.get("primary_failure", {})
    if not isinstance(choice_raw, dict) or "choice" not in choice_raw:
        raise EngineError("Missing choice in primary_failure answer")
    choice_val = choice_raw.get("choice")
    if choice_val not in CHOICE_ENUM:
        raise EngineError(f"Invalid choice value: {choice_val}")
    raw_c_conf = choice_raw.get("confidence", 0.0)
    if type(raw_c_conf) not in (int, float) or not math.isfinite(raw_c_conf) or not (0.0 <= raw_c_conf <= 1.0):
        raise EngineError("Choice confidence must be a finite number between 0.0 and 1.0")
    choice_conf = float(raw_c_conf)
    choice_reason = (
        f"Primary failure classified as {choice_val}"
        if choice_val != "none"
        else "No material failure detected"
    )

    # 2. Extract Score (production readiness)
    score_raw = answers.get("production_readiness", {})
    if not isinstance(score_raw, dict) or "score" not in score_raw:
        raise EngineError("Missing score in production_readiness answer")
    raw_s = score_raw.get("score")
    if type(raw_s) not in (int, float) or not math.isfinite(raw_s) or not (0.0 <= raw_s <= 4.0):
        raise EngineError("Score value must be a finite number between 0.0 and 4.0")
    score_val = float(raw_s)
    raw_s_conf = score_raw.get("confidence", 0.0)
    if type(raw_s_conf) not in (int, float) or not math.isfinite(raw_s_conf) or not (0.0 <= raw_s_conf <= 1.0):
        raise EngineError("Score confidence must be a finite number between 0.0 and 1.0")
    score_conf = float(raw_s_conf)
    legend = score_raw.get("legend", {})
    score_int_key = str(min(4, max(0, int(round(score_val)))))
    score_reason = legend.get(score_int_key, f"Production readiness rated {score_val:.2f}/4.0")

    # 3. Extract / Compute Acceptance Noul
    explicit_conf = None
    if "noul" in answers and isinstance(answers["noul"], dict) and "noul" in answers["noul"]:
        raw_n = answers["noul"]["noul"]
        if type(raw_n) not in (int, float) or not math.isfinite(raw_n) or not (0.0 <= raw_n <= 1.0):
            raise EngineError("Noul value must be a finite number between 0.0 and 1.0")
        noul_val = float(raw_n)
        if "confidence" in answers["noul"]:
            explicit_conf = answers["noul"]["confidence"]
        noul_reason = answers["noul"].get("reason", "Overall substantive acceptance probability")
    else:
        # Synthesize from positive and negative acceptance nouls in batched response
        ready_raw = answers.get("ready_to_deliver", {}).get("noul", 0.0)
        req_raw = answers.get("requirements_met", {}).get("noul", 0.0)
        ev_raw = answers.get("evidence_sufficient", {}).get("noul", 0.0)
        for val in (ready_raw, req_raw, ev_raw):
            if type(val) not in (int, float) or not math.isfinite(val) or not (0.0 <= val <= 1.0):
                raise EngineError("Noul value must be a finite number between 0.0 and 1.0")
        ready, req_met, ev_suff = float(ready_raw), float(req_raw), float(ev_raw)

        # Candidate acceptance is bounded by ready_to_deliver, requirements_met, and evidence
        noul_val = min(ready, req_met, ev_suff)

        # Penalize if critical requirement missing or violations present
        crit_miss = answers.get("critical_requirement_missing", {}).get("noul", 0.0)
        inst_viol = answers.get("instruction_violation_present", {}).get("noul", 0.0)
        unsupp = answers.get("unsupported_claim_present", {}).get("noul", 0.0)
        contradict = answers.get("internal_contradiction_present", {}).get("noul", 0.0)
        for neg in (crit_miss, inst_viol, unsupp, contradict):
            if type(neg) not in (int, float) or not math.isfinite(neg) or not (0.0 <= neg <= 1.0):
                raise EngineError("Negative noul value must be a finite number between 0.0 and 1.0")

        max_neg = max(crit_miss, inst_viol, unsupp, contradict)
        if max_neg > 0.5:
            noul_val = min(noul_val, 1.0 - max_neg)

        noul_val = max(0.0, min(1.0, float(noul_val)))

        for k in POSITIVE_NOULS:
            if "confidence" in answers.get(k, {}):
                c = answers[k]["confidence"]
                if isinstance(c, (int, float)) and math.isfinite(c):
                    explicit_conf = c if explicit_conf is None else min(explicit_conf, c)

        noul_reason = (
            "All mandatory requirements are satisfied and output is deliverable"
            if noul_val >= 0.90
            else f"Substantive issues detected (acceptance probability {noul_val:.2f})"
        )

    if explicit_conf is not None:
        if type(explicit_conf) not in (int, float) or not math.isfinite(explicit_conf) or not (0.0 <= explicit_conf <= 1.0):
            raise EngineError("Noul confidence must be a finite number between 0.0 and 1.0")
        noul_conf = float(explicit_conf)
    else:
        # Confidence reflects distance from uncertainty band (0.5 is maximum uncertainty)
        noul_conf = max(0.0, min(1.0, 2.0 * abs(noul_val - 0.5)))

    # 4. Extract Evidence Resolvability (if present in batched response)
    evidence_res = None
    if "evidence_resolvable" in answers:
        er_raw = answers["evidence_resolvable"]
        if not isinstance(er_raw, dict) or "noul" not in er_raw:
            raise EngineError("evidence_resolvable must be an object with noul")
        raw_er = er_raw["noul"]
        if type(raw_er) not in (int, float) or not math.isfinite(raw_er) or not (0.0 <= raw_er <= 1.0):
            raise EngineError("evidence_resolvable noul must be a finite number between 0.0 and 1.0")
        er_val = float(raw_er)
        if "confidence" in er_raw and er_raw["confidence"] is not None:
            raw_er_c = er_raw["confidence"]
            if type(raw_er_c) not in (int, float) or not math.isfinite(raw_er_c) or not (0.0 <= raw_er_c <= 1.0):
                raise EngineError("evidence_resolvable confidence must be a finite number between 0.0 and 1.0")
            er_conf = float(raw_er_c)
        else:
            er_conf = 1.0
        er_reason = er_raw.get("reason", (
            "Supplied evidence is authoritative and resolvable"
            if er_val >= 0.50
            else "Supplied evidence contains unresolved conflicts, unverified claims, or requires human judgment"
        ))
        evidence_res = {
            "value": round(er_val, 4),
            "confidence": round(er_conf, 4),
            "reason": er_reason,
        }

    # 5. Extract Concerns and Repair Targets
    concerns = []
    repair_targets = []

    if evidence_res and evidence_res["value"] < 0.50:
        concerns.append(f"evidence_resolvable below threshold (probability: {evidence_res['value']:.2f})")

    # Check negative nouls
    for k in NEGATIVE_NOULS:
        if k in answers and answers[k].get("noul", 0.0) > 0.10:
            p = answers[k]["noul"]
            concerns.append(f"{k} (probability: {p:.2f})")
            if p >= 0.50:
                repair_targets.append({
                    "type": k.replace("_present", "").replace("_missing", ""),
                    "location": "candidate_output",
                    "instruction": f"Resolve detected defect: {k}."
                })

    # Check positive nouls
    for k in POSITIVE_NOULS:
        if k in answers and answers[k].get("noul", 1.0) < 0.90:
            p = answers[k]["noul"]
            concerns.append(f"{k} below threshold (probability: {p:.2f})")

    # Add triggered failure rules to concerns and repair targets
    for r in (rule_findings or []):
        if r.get("status") in ("triggered", "uncertain"):
            concerns.append(f"Rule {r['rule_id']} ({r.get('name', '')}): {r.get('status')}")
            if r.get("status") == "triggered" and r.get("repair_instruction"):
                repair_targets.append({
                    "type": r.get("category", "rule_violation"),
                    "location": "candidate_output",
                    "instruction": r["repair_instruction"]
                })

    # Add primary failure target if specific
    if choice_val not in ("none", "other") and not any(t["type"] == choice_val for t in repair_targets):
        repair_targets.insert(0, {
            "type": choice_val,
            "location": "candidate_output",
            "instruction": f"Address primary failure: {choice_val}."
        })

    semantic_obj = {
        "noul": {
            "value": round(noul_val, 4),
            "confidence": round(noul_conf, 4),
            "reason": noul_reason,
        },
        "choice": {
            "value": choice_val,
            "confidence": round(choice_conf, 4),
            "reason": choice_reason,
        },
        "score": {
            "value": round(score_val, 2),
            "confidence": round(score_conf, 4),
            "reason": score_reason,
        },
        "concerns": concerns,
        "repair_targets": repair_targets,
    }
    if evidence_res is not None:
        semantic_obj["evidence_resolvable"] = evidence_res

    return validate_semantic_evaluation(semantic_obj)


def semantic_decide(semantic_eval, thresholds, rule_findings=None, deterministic_failed=None):
    """
    Implements the Deterministic Policy Engine (Specification v1 Section 3 & 12).
    Precedence:
      Critical deterministic violation
        > Hard requirement violation
        > Evidence / uncertainty constraints
        > Noul
        > Choice
        > Score

    Returns: (decision, failed_dimensions, reason)
    Where decision is strictly one of: 'PASS', 'REPAIR', 'HUMAN REVIEW'.
    """
    rule_findings = rule_findings or []
    deterministic_failed = deterministic_failed or []
    failed_dims = list(deterministic_failed)

    # -------------------------------------------------------------
    # Stage A — Critical Deterministic Checks
    # -------------------------------------------------------------
    # Any critical failure prohibits PASS.
    critical_rules = [
        r for r in rule_findings
        if r.get("severity") == "CRITICAL" and r.get("status") != "clear"
    ]
    warning_rules = [
        r for r in rule_findings
        if r.get("severity") != "INFO" and r.get("status") == "triggered"
    ]

    for r in critical_rules + warning_rules:
        r_dim = "rule:" + r["rule_id"]
        if r_dim not in failed_dims:
            failed_dims.append(r_dim)

    # If deterministic check failed, PASS is strictly prohibited
    if deterministic_failed:
        return "REPAIR", failed_dims, "Deterministic validation failed"

    # Actionable critical failure rules route to REPAIR before residual rule uncertainty
    triggered_critical = [r for r in critical_rules if r.get("status") == "triggered"]
    if triggered_critical:
        choice = semantic_eval["choice"]
        if choice["value"] in ("insufficient_evidence", "other"):
            return "HUMAN REVIEW", failed_dims, "Evidence or correction is unresolved"
        if choice["confidence"] < thresholds["confidence_min"]:
            return "HUMAN REVIEW", failed_dims, "Low semantic confidence"
        ev_res = semantic_eval.get("evidence_resolvable")
        if ev_res is not None:
            if ev_res["value"] < 0.50:
                return "HUMAN REVIEW", failed_dims, "Unresolved source authority or evidence conflict"
            if ev_res["confidence"] < thresholds["confidence_min"]:
                return "HUMAN REVIEW", failed_dims, "Low evidence resolvability confidence"
        return "REPAIR", failed_dims, "Triggered critical failure rules"

    # If critical rule is in uncertain state and no actionable failure is triggered, human review is mandatory
    if any(r.get("status") == "uncertain" for r in critical_rules):
        return "HUMAN REVIEW", failed_dims, "Failure-rule probability in uncertainty band"

    # -------------------------------------------------------------
    # Stage B — Semantic Confidence Check
    # -------------------------------------------------------------
    noul = semantic_eval["noul"]
    choice = semantic_eval["choice"]
    score = semantic_eval["score"]
    ev_res = semantic_eval.get("evidence_resolvable")

    # All semantic dimensions must meet confidence threshold
    confs = [noul["confidence"], choice["confidence"], score["confidence"]]
    if ev_res is not None:
        confs.append(ev_res["confidence"])
    min_confidence = min(confs)
    if min_confidence < thresholds["confidence_min"]:
        return "HUMAN REVIEW", failed_dims, "Low semantic confidence"

    # -------------------------------------------------------------
    # Stage C — Acceptance Gates (PASS)
    # -------------------------------------------------------------
    # All mandatory gates must pass:
    # 1. No critical rules triggered
    # 2. noul.value >= accept_min
    # 3. score.value >= score_min
    # 4. choice.value == 'none'
    # 5. no blocking warning rules
    # 6. evidence is safely resolvable
    if noul["value"] < thresholds["accept_min"]:
        failed_dims.append("noul_acceptance")
    if score["value"] < thresholds["score_min"]:
        failed_dims.append("production_readiness")
    if choice["value"] != "none":
        failed_dims.append("primary_failure")
    if ev_res is not None and ev_res["value"] < 0.50:
        failed_dims.append("evidence_resolvability")

    for r in warning_rules:
        r_dim = "rule:" + r["rule_id"]
        if r_dim not in failed_dims:
            failed_dims.append(r_dim)

    if not failed_dims and choice["value"] == "none":
        return "PASS", [], "All configured gates and semantic thresholds passed"

    # -------------------------------------------------------------
    # Stage D & E — Evaluation in Uncertainty Band / Repair / Human Review
    # -------------------------------------------------------------
    # Check for unresolved evidence or non-actionable choice categories
    if choice["value"] in ("insufficient_evidence", "other"):
        return "HUMAN REVIEW", failed_dims, "Evidence or correction is unresolved"

    if ev_res is not None and ev_res["value"] < 0.50:
        return "HUMAN REVIEW", failed_dims, "Unresolved source authority or evidence conflict"

    if choice["value"] == "none" and not any(r.get("status") == "triggered" for r in rule_findings):
        # Failed gates without an actionable failure class
        return "HUMAN REVIEW", failed_dims, "Failed gates without an actionable failure class"

    # If noul is in the uncertainty band (between risk_max and accept_min / failure_min)
    if thresholds["risk_max"] < (1.0 - noul["value"]) < thresholds["failure_min"]:
        return "HUMAN REVIEW", failed_dims, "Noul judgment in uncertainty band"

    # If an identifiable failure exists with an actionable target, route to REPAIR
    return "REPAIR", failed_dims, f"Confident actionable failure ({choice['value']})"
