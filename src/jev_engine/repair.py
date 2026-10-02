CORRECTIONS = {
    "requirements_met": "Satisfy every original request and locked requirement; preserve correct portions.",
    "critical_requirement_missing": "Restore the missing mandatory deliverable without changing the task.",
    "instruction_violation_present": "Remove instruction/constraint violations.",
    "internal_contradiction_present": "Resolve conflicting statements using supplied evidence.",
    "unsupported_claim_present": "Remove or explicitly qualify unsupported factual claims; invent no evidence.",
    "evidence_sufficient": "Do not invent missing evidence. Human input is required.",
    "ready_to_deliver": "Correct the identified delivery blockers.",
    "production_readiness": "Improve practical usability only where identified defects require it.",
    "primary_failure": "Correct the classified failure without changing correct content.",
    "candidate_empty": "Return the requested deliverable.",
    "required_substrings": "Include the exact required substrings from deterministic constraints.",
    "forbidden_substrings": "Remove the exact forbidden substrings.",
    "max_chars": "Meet the deterministic character limit using Python character counting.",
    "json_required_fields": "Restore the exact required top-level JSON keys without changing valid values.",
    "valid_json": "Return strictly valid JSON, without Markdown fences.",
}

def repair_payload(state, failed, primary, checks, rule_findings=None, repair_targets=None):
    targeted = [r for r in (rule_findings or []) if r["status"] == "triggered" and r["severity"] != "INFO"]
    actions = [CORRECTIONS.get(x, "Correct the named failure") for x in failed if not x.startswith("rule:")] + [r["repair_instruction"] for r in targeted]
    if repair_targets:
        for t in repair_targets:
            inst = t.get("instruction")
            if inst and inst not in actions:
                actions.append(inst)
    payload = {"original_request": state["original_request"],
            "locked_requirements": state["locked_requirements"] + state["known_constraints"],
            "previous_candidate": state["candidate_output"],
            "failed_dimensions": failed, "primary_failure": primary,
            "failure_rules": [{k:r[k] for k in ("rule_id", "name", "severity", "probability", "repair_instruction")} for r in targeted],
            "required_correction": {
                "rule": "Repair only the identified failures. Preserve all content that already satisfies the request. Do not introduce unsupported information or unrelated changes. Return only the corrected candidate.",
                "actions": actions,
                "available_evidence": state["available_evidence"],
                **({"preservation_reference":state["previous_candidate"]} if any(r["requires_previous_candidate"] for r in targeted) and state.get("previous_candidate") else {}),
                "deterministic_constraints": checks}}
    if repair_targets:
        payload["repair_targets"] = repair_targets
    return payload
