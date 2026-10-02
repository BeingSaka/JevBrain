"""
Runs the 36-case Noul Benchmark v1.0 against the current Jev implementation
using noul_benchmark_v1_locked.json as the immutable source of truth.
Validates the canonical fixture against noul_benchmark_v1_integrity.txt before any evaluation.
"""
import copy
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from validate_fixture import validate as validate_fixture_integrity
from jev_engine.__main__ import load_env
from jev_engine.jev_client import JevClient
from jev_engine.normalize import normalize, deterministic
from jev_engine.failure_rules import load_packs, applicable, questions_for, findings_for
from jev_engine.semantic import extract_semantic_evaluation, semantic_decide

def run_benchmark():
    # MANDATORY PRE-RUN GATE: Validate canonical fixture against integrity specification
    print("=" * 80)
    print("EXECUTING MANDATORY PRE-RUN INTEGRITY GATE")
    print("=" * 80)
    validate_fixture_integrity()
    print("Integrity verification complete. Proceeding to evaluation.\n")

    env_file = ROOT / ".env"
    if env_file.exists():
        load_env(str(env_file))

    profile = json.loads((ROOT / "evaluators/universal.json").read_text(encoding="utf-8"))
    thresholds = json.loads((ROOT / "config/thresholds.json").read_text(encoding="utf-8"))
    rules = load_packs([str(ROOT / "rules/universal.json")], profile)
    benchmark_fixture = json.loads((ROOT / "benchmarks/noul_benchmark_v1_locked.json").read_text(encoding="utf-8"))
    cases = benchmark_fixture["cases"]

    client = JevClient()
    results = []

    print(f"Starting evaluation of {len(cases)} canonical benchmark cases...")
    cache_path = ROOT / "benchmarks/.api_cache.json"
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    EXPECTED_MAP = {
        "ACCEPT": "PASS",
        "REPAIR": "REPAIR",
        "HUMAN_REVIEW": "HUMAN REVIEW",
    }

    for idx, case in enumerate(cases):
        case_id = case["case_id"]
        gold_label = case["gold_label"]
        expected_decision = EXPECTED_MAP[gold_label]
        candidate = case["candidate_output"]

        input_fields = {
            "original_request": case["requirement"],
            "locked_requirements": [case["requirement"]],
            "known_constraints": [],
            "available_evidence": case["available_evidence"],
            "candidate_output": case["candidate_output"],
            "output_type": "text",
            "deterministic_checks": {}
        }
        state, checks = normalize(input_fields)
        failed = deterministic(candidate, checks)
        active = applicable(rules, state, checks)

        if failed:
            actual_noul = 0.0
            actual_conf = 1.0
            actual_decision = "REPAIR"
            reason = "Deterministic validation failed"
            sem_eval = None
        else:
            questions = questions_for(profile, active)
            evaluation_state = dict(state)
            evaluation_state["deterministic_findings"] = list(failed)
            evaluation_state["triggered_rule_ids"] = []
            if rules:
                evaluation_state["deterministic_check_results"] = {"failed": failed, "configured": checks}

            raw_response = None
            if case_id in cache:
                raw_response = cache[case_id]
            else:
                try:
                    raw_response = client.evaluate(evaluation_state, questions)
                    cache[case_id] = raw_response
                    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
                except Exception as e:
                    actual_noul = 0.0
                    actual_conf = 0.0
                    actual_decision = "HUMAN REVIEW"
                    reason = f"Evaluator failure: {e}"
                    sem_eval = None

            if raw_response is not None:
                try:
                    findings = findings_for(active, failed, raw_response, thresholds, set())
                    sem_eval = extract_semantic_evaluation(raw_response, state, checks, findings)
                    actual_decision, failed_dims, reason = semantic_decide(sem_eval, thresholds, findings, failed)

                    actual_noul = sem_eval["noul"]["value"]
                    actual_conf = min(
                        sem_eval["noul"]["confidence"],
                        sem_eval["choice"]["confidence"],
                        sem_eval["score"]["confidence"],
                    )
                except Exception as e:
                    actual_noul = 0.0
                    actual_conf = 0.0
                    actual_decision = "HUMAN REVIEW"
                    reason = f"Extraction/policy failure: {e}"
                    sem_eval = None

        match = (actual_decision == expected_decision)
        status_str = "PASS" if match else "FAIL"

        res_entry = {
            "case_id": case_id,
            "gold_label": gold_label,
            "actual_noul": actual_noul,
            "confidence": actual_conf,
            "actual_decision": actual_decision,
            "expected_behavior": expected_decision,
            "status": status_str,
            "reason": reason,
            "case": case,
            "semantic_eval": sem_eval,
        }
        results.append(res_entry)
        print(f"[{idx+1:02d}/36] {case_id} | Gold: {gold_label:<12} | Act: {actual_decision:<12} | Noul: {actual_noul:.2f} | Conf: {actual_conf:.2f} | {status_str}")

    # Save detailed baseline results
    results_path = ROOT / "benchmarks/baseline_results.json"
    results_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nDetailed results saved to {results_path}")

    # Summary calculations
    total = len(results)
    correct = sum(1 for r in results if r["status"] == "PASS")
    failed = total - correct

    false_pass = sum(1 for r in results if r["actual_decision"] == "PASS" and r["expected_behavior"] != "PASS")
    false_repair = sum(1 for r in results if r["actual_decision"] == "REPAIR" and r["expected_behavior"] != "REPAIR")

    gold_accepts = sum(1 for r in results if r["expected_behavior"] == "PASS")
    true_accepts = sum(1 for r in results if r["actual_decision"] == "PASS" and r["expected_behavior"] == "PASS")
    total_actual_pass = sum(1 for r in results if r["actual_decision"] == "PASS")

    accept_recall = (true_accepts / gold_accepts) if gold_accepts else 0.0
    pass_precision = (true_accepts / total_actual_pass) if total_actual_pass else 0.0

    crit_escapes = sum(1 for r in results if r["actual_decision"] == "PASS" and r["case"].get("critical_violation"))
    unsupported_escapes = sum(1 for r in results if r["actual_decision"] == "PASS" and "unsupported" in r["case"].get("gold_reason", "").lower())
    hr_auto_pass = sum(1 for r in results if r["actual_decision"] == "PASS" and r["expected_behavior"] == "HUMAN REVIEW")

    # Noul distribution by gold class
    classes = ["ACCEPT", "REPAIR", "HUMAN_REVIEW"]
    dist = {}
    for c in classes:
        nouls = [r["actual_noul"] for r in results if r["gold_label"] == c]
        if nouls:
            dist[c] = {
                "count": len(nouls),
                "mean": round(sum(nouls) / len(nouls), 4),
                "min": round(min(nouls), 4),
                "max": round(max(nouls), 4),
            }
        else:
            dist[c] = {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}

    print("\n" + "=" * 80)
    print("NOUL BENCHMARK v1.0 BASELINE EXECUTION REPORT")
    print("=" * 80)
    print("\nCASE RESULTS TABLE:")
    print("case_id | gold_label   | actual_noul | confidence | actual decision | expected behavior | PASS/FAIL | reason")
    print("-" * 120)
    for r in results:
        print(f"{r['case_id']:<7} | {r['gold_label']:<12} | {r['actual_noul']:<11.4f} | {r['confidence']:<10.4f} | {r['actual_decision']:<15} | {r['expected_behavior']:<17} | {r['status']:<9} | {r['reason']}")

    print("\nSUMMARY METRICS:")
    print(f"- Total benchmark cases: {total}")
    print(f"- Correct cases: {correct}")
    print(f"- Failed cases: {failed}")
    print(f"- False PASS count: {false_pass}")
    print(f"- False REPAIR count: {false_repair}")
    print(f"- ACCEPT recall: {accept_recall:.1%} ({true_accepts}/{gold_accepts})")
    print(f"- PASS precision: {pass_precision:.1%} ({true_accepts}/{total_actual_pass})")
    print(f"- Critical-violation escape count: {crit_escapes}")
    print(f"- Unsupported-claim escape count: {unsupported_escapes}")
    print(f"- HUMAN REVIEW -> automatic PASS count: {hr_auto_pass}")

    print("\nNOUL DISTRIBUTION BY GOLD CLASS:")
    for c, d in dist.items():
        print(f"  {c:<14}: count={d['count']:<2} mean={d['mean']:<6.4f} min={d['min']:<6.4f} max={d['max']:<6.4f}")

    failed_cases = [r for r in results if r["status"] == "FAIL"]
    print(f"\nFAILED CASES ({len(failed_cases)}):")
    for fc in failed_cases:
        print(f"  {fc['case_id']}: Gold={fc['gold_label']}, Expected={fc['expected_behavior']}, Actual={fc['actual_decision']} (Noul={fc['actual_noul']:.2f}, Conf={fc['confidence']:.2f}) - Reason: {fc['reason']}")

    return results

if __name__ == "__main__":
    run_benchmark()
