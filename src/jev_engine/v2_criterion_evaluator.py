"""Offline-first criterion adapter for the non-authoritative V2 shadow path."""

import json
from pathlib import Path

from .v2_shadow import evaluate_shadow, plan_shadow_evaluation


STATUSES = {"CLEAR_VIOLATION", "CLEAR_NON_VIOLATION", "AMBIGUOUS", "UNAVAILABLE"}
CRITICAL = {"FR001", "FR002", "FR003", "FR004", "FR006", "FR007", "FR008", "FR009"}
RULE_IDS = {f"FR{i:03d}" for i in range(1, 11)}


def load_criterion_profile(path):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    questions = profile.get("questions") if isinstance(profile, dict) else None
    if profile.get("shadow_version") != "2.0.0-shadow" or not isinstance(questions, dict) or set(questions) != RULE_IDS:
        raise ValueError("Invalid V2 criterion profile")
    for rule_id, contract in questions.items():
        if set(contract) != {"state_fields", "question"} or not isinstance(contract["state_fields"], list):
            raise ValueError(f"Invalid V2 criterion contract: {rule_id}")
        question = contract["question"]
        if not isinstance(question, dict) or question.get("type") != "choice" or set(question.get("criteria", {})) != STATUSES:
            raise ValueError(f"Invalid V2 criterion question: {rule_id}")
    return profile


def parse_criterion_response(response, rule_id):
    question_id = "criterion_" + rule_id
    if not isinstance(response, dict) or not isinstance(response.get("model"), str):
        raise ValueError("Invalid criterion response envelope")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != {question_id}:
        raise ValueError("Missing or unexpected criterion answer")
    answer = answers[question_id]
    if not isinstance(answer, dict) or answer.get("type") != "choice" or answer.get("choice") not in STATUSES:
        raise ValueError("Invalid criterion state")
    return answer["choice"]


def _result(rule_id, status, evidence):
    return {
        "rule_id": rule_id,
        "status": status,
        "evidence_status": "UNAVAILABLE" if status == "UNAVAILABLE" else "SUFFICIENT",
        "actionable": rule_id in CRITICAL and status == "CLEAR_VIOLATION",
        "evidence": evidence,
    }


def evaluate_with_criterion_evaluator(state, v1_authority, rules, profile, evaluator=None, deterministic_gates=(), deterministically_resolved=()):
    plan = plan_shadow_evaluation(state, rules, deterministic_gates, deterministically_resolved)
    results = []
    if evaluator is not None and not any(gate["status"] == "FAIL" for gate in plan["deterministic_gates"]):
        for rule_id in plan["routing"]["considered_rules"]:
            contract = profile["questions"][rule_id]
            criterion_state = {field: state[field] for field in contract["state_fields"] if field in state}
            question_id = "criterion_" + rule_id
            try:
                response = evaluator.evaluate(criterion_state, {question_id: contract["question"]})
                status = parse_criterion_response(response, rule_id)
                evidence = "Criterion evaluator returned a valid four-state result."
            except Exception:
                status = "UNAVAILABLE"
                evidence = "Criterion evaluator failed or returned an invalid response."
            results.append(_result(rule_id, status, evidence))
    return evaluate_shadow(
        state, v1_authority, rules, results,
        deterministic_gates=deterministic_gates,
        deterministically_resolved=deterministically_resolved,
        trusted_synthetic_fixture=False,
    )
