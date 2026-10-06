import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jev_engine.v2_shadow import (
    AUTHORITY_NOTE,
    V2_HUMAN_REVIEW,
    V2_INSUFFICIENT_EVIDENCE,
    V2_PASS,
    V2_REPAIR,
    evaluate_shadow,
    load_rules,
    validate_audit,
)
from jev_engine.v2_criterion_evaluator import (
    evaluate_with_criterion_evaluator,
    load_criterion_profile,
    parse_criterion_response,
)
from scripts.run_v2_shadow import main as run_v2_main


RULES = ROOT / "rules" / "v2_shadow.json"
CRITERIA_PROFILE = ROOT / "evaluators" / "v2_shadow.json"
LOCKED_V1 = (
    "benchmarks/noul_benchmark_v1_locked.json",
    "benchmarks/noul_benchmark_v1_integrity.txt",
    "benchmarks/noul_benchmark_v1.json",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def authority():
    return {"decision": "HUMAN REVIEW", "reason": "V1 remains authoritative."}


def critical_result(rule_id, status, evidence_status="SUFFICIENT", actionable=True):
    return {
        "rule_id": rule_id,
        "status": status,
        "evidence_status": evidence_status,
        "actionable": actionable,
        "evidence": "fixed test result",
    }


def choice_response(question_id, status, **extra):
    answer = {"type": "choice", "choice": status}
    answer.update(extra)
    return {"model": "fixture", "answers": {question_id: answer}, "usage": {"input_tokens": 0, "output_tokens": 0}}


class CriterionEvaluator:
    def __init__(self, statuses=None, error=None):
        self.statuses = statuses or {}
        self.error = error
        self.calls = []

    def evaluate(self, state, questions):
        self.calls.append({"state": state, "questions": questions})
        if self.error:
            raise self.error
        question_id = next(iter(questions))
        rule_id = question_id.removeprefix("criterion_")
        return choice_response(question_id, self.statuses.get(rule_id, "CLEAR_NON_VIOLATION"))


class V2ShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules(RULES)
        cls.criterion_profile = load_criterion_profile(CRITERIA_PROFILE)

    def evaluate(self, state=None, criteria=(), **kwargs):
        return evaluate_shadow(
            state or {"original_request": "Return status.", "candidate_output": "READY."},
            authority(),
            self.rules,
            list(criteria),
            **kwargs,
        )

    def test_v1_source_files_match_head(self):
        paths = [p for p in git("ls-files", "src/jev_engine").splitlines() if not p.endswith("v2_shadow.py")]
        self.assertTrue(paths)
        for path in paths:
            self.assertEqual(git("hash-object", path), git("rev-parse", f"HEAD:{path}"), path)

    def test_v1_cli_matches_head(self):
        self.assertEqual(git("hash-object", "run.py"), git("rev-parse", "HEAD:run.py"))

    def test_locked_v1_blobs_match_head(self):
        for path in LOCKED_V1:
            self.assertEqual(git("hash-object", path), git("rev-parse", f"HEAD:{path}"), path)

    def test_v2_failure_cannot_change_v1_authority(self):
        record = self.evaluate(criteria=[critical_result("FR003", "CLEAR_VIOLATION")])
        self.assertEqual(record["v1_authority"], authority())
        self.assertEqual(record["v2_result"], V2_REPAIR)
        self.assertEqual(record["authority_note"], AUTHORITY_NOTE)

    def test_unavailable_or_invalid_criterion_is_non_pass(self):
        unavailable = self.evaluate(criteria=[critical_result("FR003", "UNAVAILABLE")])
        invalid = self.evaluate(criteria=[critical_result("FR003", "NOT_A_STATUS")])
        self.assertNotEqual(unavailable["v2_result"], V2_PASS)
        self.assertNotEqual(invalid["v2_result"], V2_PASS)

    def test_ambiguous_relevant_critical_is_human_review(self):
        record = self.evaluate(criteria=[critical_result("FR003", "AMBIGUOUS")])
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)
        self.assertEqual(record["ambiguous_criteria"], ["FR003"])

    def test_missing_or_conflicting_evidence_is_insufficient(self):
        for evidence_status in ("MISSING", "CONFLICTING"):
            record = self.evaluate(criteria=[critical_result("FR003", "UNAVAILABLE", evidence_status)])
            self.assertEqual(record["v2_result"], V2_INSUFFICIENT_EVIDENCE)

    def test_clear_actionable_critical_violation_is_repair(self):
        record = self.evaluate(criteria=[critical_result("FR009", "CLEAR_VIOLATION")])
        self.assertEqual(record["v2_result"], V2_REPAIR)

    def test_fr007_is_skipped_without_previous_candidate(self):
        record = self.evaluate()
        skipped = {item["rule_id"]: item["reason"] for item in record["routing"]["skipped_rules"]}
        self.assertEqual(skipped["FR007"], "previous_candidate_absent")

    def test_fr006_is_skipped_without_explicit_format_contract(self):
        record = self.evaluate()
        skipped = {item["rule_id"]: item["reason"] for item in record["routing"]["skipped_rules"]}
        self.assertEqual(skipped["FR006"], "format_contract_absent")

    def test_uncertain_relevance_keeps_critical_rule_considered(self):
        record = self.evaluate()
        relevance = {item["rule_id"]: item["status"] for item in record["routing"]["relevance"]}
        self.assertEqual(relevance["FR003"], "UNCERTAIN")
        self.assertIn("FR003", record["routing"]["considered_rules"])

    def test_audit_explains_all_considered_and_skipped_rules(self):
        record = self.evaluate()
        validate_audit(record)
        accounted = set(record["routing"]["considered_rules"]) | {x["rule_id"] for x in record["routing"]["skipped_rules"]}
        self.assertEqual(accounted, {f"FR{i:03d}" for i in range(1, 11)})

    def test_v2_pass_requires_explicit_trusted_synthetic_fixture(self):
        criteria = [critical_result(rule_id, "CLEAR_NON_VIOLATION") for rule_id in ("FR001", "FR002", "FR003", "FR004", "FR008", "FR009")]
        untrusted = self.evaluate(criteria=criteria)
        trusted = self.evaluate(criteria=criteria, trusted_synthetic_fixture=True)
        self.assertNotEqual(untrusted["v2_result"], V2_PASS)
        self.assertEqual(trusted["v2_result"], V2_PASS)

    def test_all_clear_nonviolations_remain_uncalibrated_non_pass(self):
        criteria = [critical_result(rule_id, "CLEAR_NON_VIOLATION") for rule_id in ("FR001", "FR002", "FR003", "FR004", "FR008", "FR009")]
        record = self.evaluate(criteria=criteria)
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)
        self.assertIn("Calibration is unavailable", record["v2_reason"])

    def test_unavailable_relevant_critical_uses_fail_closed_state(self):
        record = self.evaluate(criteria=[critical_result("FR003", "UNAVAILABLE")])
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)
        self.assertIn("unavailable", record["v2_reason"])

    def test_skipped_criterion_result_cannot_block(self):
        record = self.evaluate(criteria=[critical_result("FR007", "CLEAR_VIOLATION")])
        self.assertNotEqual(record["v2_result"], V2_REPAIR)
        self.assertNotIn("FR007", record["routing"]["considered_rules"])

    def test_fr005_diagnostic_is_decision_neutral(self):
        baseline = self.evaluate()
        diagnostic = self.evaluate(criteria=[critical_result("FR005", "CLEAR_VIOLATION")])
        self.assertEqual(diagnostic["v2_result"], baseline["v2_result"])

    def test_fr010_diagnostic_is_decision_neutral(self):
        baseline = self.evaluate()
        diagnostic = self.evaluate(criteria=[critical_result("FR010", "CLEAR_VIOLATION")])
        self.assertEqual(diagnostic["v2_result"], baseline["v2_result"])

    def test_criterion_results_are_isolated(self):
        criteria = [critical_result(rule_id, "CLEAR_NON_VIOLATION") for rule_id in ("FR001", "FR002", "FR004", "FR008", "FR009")]
        criteria.append(critical_result("FR003", "CLEAR_VIOLATION"))
        record = self.evaluate(criteria=criteria)
        statuses = {item["rule_id"]: item["status"] for item in record["criterion_results"]}
        self.assertEqual(statuses["FR001"], "CLEAR_NON_VIOLATION")
        self.assertEqual(statuses["FR003"], "CLEAR_VIOLATION")
        self.assertEqual(record["v2_result"], V2_REPAIR)

    def test_aggregate_score_is_diagnostic_only(self):
        criteria = [critical_result(rule_id, "CLEAR_NON_VIOLATION") for rule_id in ("FR001", "FR002", "FR003", "FR004", "FR008", "FR009")]
        low = self.evaluate(criteria=criteria, diagnostic_readiness_signals={"aggregate_score": 0.0})
        high = self.evaluate(criteria=criteria, diagnostic_readiness_signals={"aggregate_score": 1.0})
        self.assertEqual(low["v2_result"], high["v2_result"])

    def test_noul_is_diagnostic_only(self):
        criteria = [critical_result(rule_id, "CLEAR_NON_VIOLATION") for rule_id in ("FR001", "FR002", "FR003", "FR004", "FR008", "FR009")]
        low = self.evaluate(criteria=criteria, diagnostic_readiness_signals={"noul": 0.0})
        high = self.evaluate(criteria=criteria, diagnostic_readiness_signals={"noul": 1.0})
        self.assertEqual(low["v2_result"], high["v2_result"])

    def test_synthetic_confidence_is_diagnostic_only(self):
        criteria = [critical_result(rule_id, "CLEAR_NON_VIOLATION") for rule_id in ("FR001", "FR002", "FR003", "FR004", "FR008", "FR009")]
        low = self.evaluate(criteria=criteria, diagnostic_readiness_signals={"synthetic_confidence": 0.0})
        high = self.evaluate(criteria=criteria, diagnostic_readiness_signals={"synthetic_confidence": 1.0})
        self.assertEqual(low["v2_result"], high["v2_result"])

    def test_deterministic_failure_precedes_semantic_result(self):
        gate = {"gate_id": "required_marker", "status": "FAIL", "actionable": True, "evidence": "Marker absent."}
        record = self.evaluate(criteria=[critical_result("FR003", "AMBIGUOUS")], deterministic_gates=[gate])
        self.assertEqual(record["v2_result"], V2_REPAIR)
        self.assertEqual(record["v2_reason"], "required_marker")

    def test_fr006_deterministic_resolution_skips_semantic(self):
        state = {
            "original_request": "Use Situation, Impact, and Next step headings.",
            "candidate_output": "Situation: Ready. Impact: None. Next step: Ship.",
            "deterministic_checks": {"required_substrings": ["Situation:", "Impact:", "Next step:"]},
        }
        record = self.evaluate(state=state, deterministically_resolved=("FR006",))
        skipped = {item["rule_id"]: item["reason"] for item in record["routing"]["skipped_rules"]}
        self.assertEqual(skipped["FR006"], "format_contract_resolved_deterministically")
        self.assertNotIn("FR006", {item["rule_id"] for item in record["criterion_results"]})

    def test_fr007_verbatim_synonym_substitution_is_deterministic_violation(self):
        state = {
            "original_request": "Add a greeting and preserve the answer verbatim.",
            "previous_candidate": "Thank you for your message.",
            "candidate_output": "Hello. Thank you for your request.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self.evaluate(state=state)
        self.assertEqual(record["v2_result"], V2_REPAIR)
        self.assertEqual(record["v2_reason"], "FR007_verbatim_preservation")
        self.assertNotIn("FR007", record["routing"]["considered_rules"])

    def test_fr007_verbatim_punctuation_change_is_deterministic_violation(self):
        state = {
            "previous_candidate": "Your notes are welcome.",
            "candidate_output": "Hello. Your notes are welcome!",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self.evaluate(state=state)
        self.assertEqual(record["v2_result"], V2_REPAIR)
        self.assertNotIn("FR007", record["routing"]["considered_rules"])

    def test_fr007_exact_preservation_keeps_semantic_path(self):
        state = {
            "previous_candidate": "Thank you for your message.",
            "candidate_output": "Hello. Thank you for your message.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self.evaluate(state=state, criteria=[critical_result("FR007", "CLEAR_NON_VIOLATION")])
        self.assertIn("FR007", record["routing"]["considered_rules"])
        self.assertFalse(any(gate["gate_id"] == "FR007_verbatim_preservation" for gate in record["deterministic_gates"]))

    def test_fr007_authorized_rewording_without_flag_keeps_semantic_path(self):
        state = {
            "previous_candidate": "Your notes are welcome.",
            "candidate_output": "Hello. We welcome your notes.",
            "allowed_changes": ["Improve wording for clarity."],
        }
        record = self.evaluate(state=state, criteria=[critical_result("FR007", "CLEAR_NON_VIOLATION")])
        self.assertIn("FR007", record["routing"]["considered_rules"])
        self.assertFalse(any(gate["gate_id"] == "FR007_verbatim_preservation" for gate in record["deterministic_gates"]))

    def test_fr007_missing_verbatim_flag_keeps_semantic_path(self):
        state = {"previous_candidate": "Old.", "candidate_output": "New."}
        record = self.evaluate(state=state, criteria=[critical_result("FR007", "AMBIGUOUS")])
        self.assertIn("FR007", record["routing"]["considered_rules"])
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)

    def test_fr007_false_verbatim_flag_keeps_semantic_path(self):
        state = {
            "previous_candidate": "Old.",
            "candidate_output": "New.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": False},
        }
        record = self.evaluate(state=state, criteria=[critical_result("FR007", "AMBIGUOUS")])
        self.assertIn("FR007", record["routing"]["considered_rules"])
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)

    def test_fr007_true_flag_without_usable_previous_candidate_fails_safe(self):
        state = {
            "previous_candidate": "",
            "candidate_output": "Hello.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self.evaluate(state=state)
        self.assertIn("FR007", record["routing"]["considered_rules"])
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)
        self.assertFalse(any(gate["gate_id"] == "FR007_verbatim_preservation" for gate in record["deterministic_gates"]))

    def test_fr007_deterministic_violation_overrides_injected_nonviolation(self):
        state = {
            "previous_candidate": "Keep exactly.",
            "candidate_output": "Keep approximately.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self.evaluate(state=state, criteria=[critical_result("FR007", "CLEAR_NON_VIOLATION")])
        statuses = {item["rule_id"]: item["status"] for item in record["criterion_results"]}
        self.assertEqual(statuses["FR007"], "CLEAR_VIOLATION")
        self.assertEqual(record["v2_result"], V2_REPAIR)

    def test_fr007_exact_substring_precheck_cannot_authorize_pass(self):
        state = {
            "previous_candidate": "Keep exactly.",
            "candidate_output": "Hello. Keep exactly.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self.evaluate(state=state, criteria=[critical_result("FR007", "CLEAR_NON_VIOLATION")])
        self.assertNotEqual(record["v2_result"], V2_PASS)
        self.assertIn("FR007", record["routing"]["considered_rules"])

    def test_criterion_adapter_offline_default_makes_zero_calls(self):
        evaluator = CriterionEvaluator()
        record = evaluate_with_criterion_evaluator(
            {"original_request": "Return status.", "candidate_output": "READY."},
            authority(), self.rules, self.criterion_profile, evaluator=None,
        )
        self.assertEqual(evaluator.calls, [])
        self.assertNotEqual(record["v2_result"], V2_PASS)

    def test_criterion_adapter_calls_once_per_considered_rule(self):
        evaluator = CriterionEvaluator()
        record = evaluate_with_criterion_evaluator(
            {"original_request": "Return status.", "candidate_output": "READY."},
            authority(), self.rules, self.criterion_profile, evaluator=evaluator,
        )
        self.assertEqual(len(evaluator.calls), len(record["routing"]["considered_rules"]))
        self.assertTrue(all(len(call["questions"]) == 1 for call in evaluator.calls))

    def test_criterion_adapter_projects_rule_specific_state(self):
        evaluator = CriterionEvaluator()
        state = {
            "original_request": "State the date.", "available_evidence": "Date: tomorrow.",
            "candidate_output": "Tomorrow.", "previous_candidate": "Yesterday.",
            "allowed_changes": ["Update date."], "locked_requirements": ["Be accurate."],
            "known_constraints": ["One line."], "irrelevant_secret": "must not be sent",
        }
        evaluate_with_criterion_evaluator(state, authority(), self.rules, self.criterion_profile, evaluator=evaluator)
        fr003 = next(call for call in evaluator.calls if "criterion_FR003" in call["questions"])
        self.assertEqual(set(fr003["state"]), {"original_request", "available_evidence", "candidate_output"})
        self.assertNotIn("irrelevant_secret", fr003["state"])

    def test_criterion_adapter_skips_deterministically_resolved_rules(self):
        evaluator = CriterionEvaluator()
        state = {
            "original_request": "Preserve verbatim and use headings.",
            "previous_candidate": "Keep exactly.", "candidate_output": "Changed.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True, "required_substrings": ["Heading:"]},
        }
        record = evaluate_with_criterion_evaluator(
            state, authority(), self.rules, self.criterion_profile, evaluator=evaluator,
            deterministically_resolved=("FR006",),
        )
        called = {next(iter(call["questions"])).removeprefix("criterion_") for call in evaluator.calls}
        self.assertNotIn("FR006", called)
        self.assertNotIn("FR007", called)
        self.assertEqual(record["v2_result"], V2_REPAIR)

    def test_criterion_parser_accepts_exact_four_states(self):
        for status in ("CLEAR_VIOLATION", "CLEAR_NON_VIOLATION", "AMBIGUOUS", "UNAVAILABLE"):
            self.assertEqual(parse_criterion_response(choice_response("criterion_FR003", status), "FR003"), status)

    def test_criterion_adapter_maps_malformed_and_exception_to_unavailable(self):
        malformed = CriterionEvaluator()
        malformed.evaluate = lambda state, questions: {"answers": {}}
        failed = CriterionEvaluator(error=RuntimeError("offline fixture failure"))
        for evaluator in (malformed, failed):
            record = evaluate_with_criterion_evaluator(
                {"original_request": "Return status.", "candidate_output": "READY."},
                authority(), self.rules, self.criterion_profile, evaluator=evaluator,
            )
            statuses = {item["status"] for item in record["criterion_results"] if item["rule_id"] in record["routing"]["considered_rules"]}
            self.assertIn("UNAVAILABLE", statuses)
            self.assertNotEqual(record["v2_result"], V2_PASS)

    def test_criterion_adapter_critical_ambiguity_and_unavailable_cannot_pass(self):
        for status in ("AMBIGUOUS", "UNAVAILABLE"):
            evaluator = CriterionEvaluator({"FR003": status})
            record = evaluate_with_criterion_evaluator(
                {"original_request": "Return status.", "candidate_output": "READY."},
                authority(), self.rules, self.criterion_profile, evaluator=evaluator,
            )
            self.assertNotEqual(record["v2_result"], V2_PASS)

    def test_criterion_adapter_diagnostics_are_decision_neutral(self):
        baseline = evaluate_with_criterion_evaluator(
            {"original_request": "Return status.", "candidate_output": "READY."},
            authority(), self.rules, self.criterion_profile, evaluator=CriterionEvaluator(),
        )
        diagnostic = evaluate_with_criterion_evaluator(
            {"original_request": "Return status.", "candidate_output": "READY."},
            authority(), self.rules, self.criterion_profile,
            evaluator=CriterionEvaluator({"FR005": "CLEAR_VIOLATION", "FR010": "CLEAR_VIOLATION"}),
        )
        self.assertEqual(diagnostic["v2_result"], baseline["v2_result"])

    def test_criterion_adapter_ignores_scores_probabilities_and_confidence(self):
        raw = choice_response(
            "criterion_FR003", "CLEAR_NON_VIOLATION",
            probabilities={"untrusted": 1}, confidence=-999, noul=1, aggregate_score=1,
        )
        self.assertEqual(parse_criterion_response(raw, "FR003"), "CLEAR_NON_VIOLATION")

    def test_criterion_adapter_cannot_enable_synthetic_pass(self):
        record = evaluate_with_criterion_evaluator(
            {"original_request": "Return status.", "candidate_output": "READY."},
            authority(), self.rules, self.criterion_profile, evaluator=CriterionEvaluator(),
        )
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)

    def test_runner_exposes_disabled_live_semantic_boundary(self):
        text = (ROOT / "scripts/run_v2_shadow.py").read_text(encoding="utf-8")
        self.assertIn("--live-semantic", text)
        self.assertGreater(text.index("from jev_engine.jev_client import JevClient"), text.index("if args.live_semantic"))

    def _run_cli(self, state, criteria=None, live=False, evaluator_factory=None):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            directory = Path(directory)
            paths = {name: directory / f"{name}.json" for name in ("input", "criteria", "authority", "output")}
            paths["input"].write_text(json.dumps(state), encoding="utf-8")
            paths["criteria"].write_text(json.dumps(criteria or []), encoding="utf-8")
            paths["authority"].write_text(json.dumps(authority()), encoding="utf-8")
            argv = ["--input", str(paths["input"]), "--v1-authority", str(paths["authority"]), "--output", str(paths["output"])]
            if live:
                argv.append("--live-semantic")
            else:
                argv.extend(["--criteria", str(paths["criteria"])])
            self.assertEqual(run_v2_main(argv, evaluator_factory=evaluator_factory), 0)
            return json.loads(paths["output"].read_text(encoding="utf-8"))

    def test_runner_offline_never_constructs_evaluator(self):
        def forbidden_factory():
            self.fail("offline path constructed evaluator")
        record = self._run_cli({"original_request": "Return status.", "candidate_output": "READY."}, evaluator_factory=forbidden_factory)
        self.assertNotEqual(record["v2_result"], V2_PASS)

    def test_runner_live_opt_in_constructs_injected_evaluator(self):
        evaluator = CriterionEvaluator()
        constructions = []
        record = self._run_cli(
            {"original_request": "Return status.", "candidate_output": "READY."},
            live=True, evaluator_factory=lambda: constructions.append(True) or evaluator,
        )
        self.assertEqual(constructions, [True])
        self.assertGreater(len(evaluator.calls), 0)
        self.assertEqual(record["v1_authority"], authority())

    def test_runner_live_path_cannot_authorize_synthetic_pass(self):
        record = self._run_cli(
            {"original_request": "Return status.", "candidate_output": "READY."},
            live=True, evaluator_factory=lambda: CriterionEvaluator(),
        )
        self.assertEqual(record["v2_result"], V2_HUMAN_REVIEW)

    def test_runner_live_deterministic_violation_skips_semantic_calls(self):
        evaluator = CriterionEvaluator()
        state = {
            "previous_candidate": "Keep exactly.", "candidate_output": "Changed.",
            "deterministic_checks": {"preserve_previous_candidate_verbatim": True},
        }
        record = self._run_cli(state, live=True, evaluator_factory=lambda: evaluator)
        self.assertEqual(evaluator.calls, [])
        self.assertEqual(record["v2_result"], V2_REPAIR)
        self.assertEqual(record["v1_authority"], authority())

    def test_runner_skips_mechanically_resolved_fr006(self):
        evaluator = CriterionEvaluator()
        record = self._run_cli(
            {
                "original_request": "Use a Status heading.",
                "candidate_output": "READY.",
                "deterministic_checks": {"required_substrings": ["Status:"]},
            },
            live=True,
            evaluator_factory=lambda: evaluator,
        )
        called = {next(iter(call["questions"])).removeprefix("criterion_") for call in evaluator.calls}
        self.assertNotIn("FR006", called)
        skipped = {item["rule_id"]: item["reason"] for item in record["routing"]["skipped_rules"]}
        self.assertEqual(skipped["FR006"], "format_contract_resolved_deterministically")

    def test_runner_unresolved_format_reaches_fr006(self):
        evaluator = CriterionEvaluator()
        self._run_cli(
            {
                "original_request": "Use headings and make Next step a complete action sentence.",
                "candidate_output": "Situation: Ready. Impact: None. Next step: Observe.",
                "deterministic_checks": {"required_substrings": ["Situation:", "Impact:", "Next step:"]},
            },
            live=True,
            evaluator_factory=lambda: evaluator,
        )
        called = {next(iter(call["questions"])).removeprefix("criterion_") for call in evaluator.calls}
        self.assertIn("FR006", called)

    def test_shadow_module_and_runner_have_no_network_or_v1_side_effect_imports(self):
        for path in (ROOT / "src/jev_engine/v2_shadow.py", ROOT / "src/jev_engine/v2_criterion_evaluator.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("jev_engine.semantic", text)
            self.assertNotIn("jev_engine.jev_client", text)
            self.assertNotIn("urllib", text)
            self.assertNotIn("requests", text)
            self.assertNotIn("http", text)

    def test_development_controls_remain_pending_human_reviews(self):
        data = json.loads((ROOT / "benchmarks/development/v2_controls.json").read_text(encoding="utf-8"))
        self.assertEqual(data["human_review_status"], "PENDING_TWO_INDEPENDENT_HUMAN_REVIEWS")
        self.assertEqual(len(data["cases"]), 22)


if __name__ == "__main__":
    unittest.main()
