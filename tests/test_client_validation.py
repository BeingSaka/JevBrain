import copy
import math
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jev_engine.jev_client import validate_response, number
from jev_engine.normalize import EngineError
from jev_engine.engine import Engine

QUESTIONS = {
    "primary_failure": {
        "type": "choice",
        "instructions": "Identify primary failure.",
        "criteria": {
            "none": "No failure.",
            "unsupported_claim": "Unsupported claim."
        }
    },
    "production_readiness": {
        "type": "score",
        "instructions": "Rate usability on 0-4 scale.",
        "criteria": [
            "Level 0",
            "Level 1",
            "Level 2",
            "Level 3",
            "Level 4"
        ]
    }
}

def make_valid_response(score=3.0, probs=None, prob_sum_drift=0.0):
    if probs is None:
        probs = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0, "4": 0.0}
    return {
        "model": "jev-1.13.0",
        "answers": {
            "primary_failure": {
                "type": "choice",
                "choice": "none",
                "confidence": 0.95,
                "probabilities": {"none": 0.95, "unsupported_claim": 0.05}
            },
            "production_readiness": {
                "type": "score",
                "score": score,
                "confidence": 0.90,
                "probabilities": dict(probs),
                "legend": {str(i): f"Level {i}" for i in range(5)}
            }
        },
        "usage": {"input_tokens": 100, "output_tokens": 10}
    }


class TestClientValidation(unittest.TestCase):
    """
    Unit tests for general validator behavior in jev_client.validate_response
    covering all Phase 6 requirements.
    """

    # 1. Exact valid score/probabilities -> accepted
    def test_01_exact_valid_score_accepted(self):
        resp = make_valid_response(score=3.0, probs={"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0, "4": 0.0})
        validated = validate_response(resp, QUESTIONS)
        self.assertEqual(validated["answers"]["production_readiness"]["score"], 3.0)

    # 2. Tiny floating-point discrepancy -> accepted
    def test_02_tiny_float_discrepancy_accepted(self):
        # 3.94 explicit vs weighted 3.92 (diff 0.020000000000000018)
        probs = {"0": 0.0, "1": 0.01, "2": 0.01, "3": 0.03, "4": 0.95}
        resp = make_valid_response(score=3.94, probs=probs)
        validated = validate_response(resp, QUESTIONS)
        self.assertEqual(validated["answers"]["production_readiness"]["score"], 3.94)

    # 3. Legitimate rounding-consistent discrepancy -> accepted
    def test_03_rounding_consistent_discrepancy_accepted(self):
        # 3.27 explicit vs weighted 3.30 (diff 0.030 due to 2-decimal discretization of 5 levels)
        probs = {"0": 0.0, "1": 0.08, "2": 0.14, "3": 0.18, "4": 0.60}
        resp = make_valid_response(score=3.27, probs=probs)
        validated = validate_response(resp, QUESTIONS)
        self.assertEqual(validated["answers"]["production_readiness"]["score"], 3.27)

    # 4. Probabilities with tiny normalization drift -> correctly handled
    def test_04_normalization_drift_accepted(self):
        # Probabilities sum to 0.99 (drift 0.01 within allowed 0.01 bound), unnormalized weighted 3.89, normalized 3.9293, score 3.92
        probs = {"0": 0.0, "1": 0.0, "2": 0.01, "3": 0.05, "4": 0.93}
        resp = make_valid_response(score=3.92, probs=probs)
        validated = validate_response(resp, QUESTIONS)
        self.assertEqual(validated["answers"]["production_readiness"]["score"], 3.92)

    # 5. Material score/probability disagreement -> rejected
    def test_05_material_score_probability_disagreement_rejected(self):
        probs = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0, "4": 0.0}  # weighted = 3.0
        # Discrepancy > 0.05 (e.g. 3.10 vs 3.00, diff 0.10)
        resp = make_valid_response(score=3.10, probs=probs)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid weighted score", str(ctx.exception))

        # Gross material disagreement (score 1.0 vs weighted 3.0)
        resp2 = make_valid_response(score=1.0, probs=probs)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp2, QUESTIONS)
        self.assertIn("Invalid weighted score", str(ctx.exception))

    # 6. Probability sum materially invalid -> rejected
    def test_06_materially_invalid_probability_sum_rejected(self):
        # Sum = 0.95 (drift 0.05 > 0.01)
        probs_low = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.95, "4": 0.0}
        resp_low = make_valid_response(score=3.0, probs=probs_low)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp_low, QUESTIONS)
        self.assertIn("Evaluation probabilities do not sum to one", str(ctx.exception))

        # Sum = 1.05 (drift 0.05 > 0.01)
        probs_high = {"0": 0.05, "1": 0.0, "2": 0.0, "3": 1.0, "4": 0.0}
        resp_high = make_valid_response(score=3.0, probs=probs_high)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp_high, QUESTIONS)
        self.assertIn("Evaluation probabilities do not sum to one", str(ctx.exception))

    # 7. Negative probability -> rejected
    def test_07_negative_probability_rejected(self):
        probs = {"0": -0.05, "1": 0.05, "2": 0.0, "3": 1.0, "4": 0.0}
        resp = make_valid_response(score=3.0, probs=probs)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

    # 8. Probability > 1 -> rejected
    def test_08_probability_greater_than_one_rejected(self):
        probs = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.05, "4": 0.0}
        resp = make_valid_response(score=3.0, probs=probs)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

    # 9. NaN score -> rejected
    def test_09_nan_score_rejected(self):
        resp = make_valid_response(score=float("nan"))
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

    # 10. Infinity score -> rejected
    def test_10_infinity_score_rejected(self):
        resp = make_valid_response(score=float("inf"))
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

        resp_neg_inf = make_valid_response(score=float("-inf"))
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp_neg_inf, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

    # 11. NaN probability -> rejected
    def test_11_nan_probability_rejected(self):
        probs = {"0": float("nan"), "1": 0.0, "2": 0.0, "3": 1.0, "4": 0.0}
        resp = make_valid_response(score=3.0, probs=probs)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

    # 12. Missing score/probability data -> rejected if required by contract
    def test_12_missing_score_probability_data_rejected(self):
        # Missing probabilities
        resp_no_probs = make_valid_response(score=3.0)
        del resp_no_probs["answers"]["production_readiness"]["probabilities"]
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp_no_probs, QUESTIONS)
        self.assertIn("Invalid evaluation distribution", str(ctx.exception))

        # Missing score
        resp_no_score = make_valid_response(score=3.0)
        del resp_no_score["answers"]["production_readiness"]["score"]
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp_no_score, QUESTIONS)
        self.assertIn("Invalid numeric evaluation result", str(ctx.exception))

        # Missing legend
        resp_no_legend = make_valid_response(score=3.0)
        del resp_no_legend["answers"]["production_readiness"]["legend"]
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp_no_legend, QUESTIONS)
        self.assertIn("Score legend missing", str(ctx.exception))

    # 13. Wrong probability labels/range -> rejected
    def test_13_wrong_probability_labels_rejected(self):
        # Keys 1..5 instead of 0..4
        wrong_probs = {"1": 0.0, "2": 0.0, "3": 0.0, "4": 1.0, "5": 0.0}
        resp = make_valid_response(score=3.0, probs=wrong_probs)
        with self.assertRaises(EngineError) as ctx:
            validate_response(resp, QUESTIONS)
        self.assertIn("Invalid evaluation distribution", str(ctx.exception))

    # 14. Valid response behavior remains unchanged
    def test_14_valid_response_behavior_unchanged(self):
        resp = make_valid_response(score=4.0, probs={"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0, "4": 1.0})
        validated = validate_response(resp, QUESTIONS)
        self.assertEqual(validated["model"], "jev-1.13.0")
        self.assertEqual(validated["answers"]["production_readiness"]["score"], 4.0)
        self.assertEqual(validated["answers"]["primary_failure"]["choice"], "none")

    # 15. Invalid provider response still cannot produce automatic PASS
    def test_15_invalid_provider_response_never_automatic_pass(self):
        class MockEvaluator:
            name = "mock"
            def evaluate(self, state, questions):
                # Return materially inconsistent response
                return make_valid_response(score=1.0, probs={"0": 0.0, "1": 0.0, "2": 0.0, "3": 1.0, "4": 0.0})

        class MockLogger:
            def write(self, event): pass

        profile = {
            "name": "test_profile",
            "version": 1,
            "questions": copy.deepcopy(QUESTIONS)
        }
        thresholds = {
            "accept_min": 0.9,
            "risk_max": 0.1,
            "failure_min": 0.8,
            "score_min": 3.5,
            "confidence_min": 0.65
        }
        engine = Engine(
            evaluator=MockEvaluator(),
            worker=None,
            profile=profile,
            thresholds=thresholds,
            logger=MockLogger(),
            rules=[],
            semantic_evaluation_enabled=True
        )
        input_data = {
            "original_request": "Test request",
            "locked_requirements": ["Requirement 1"],
            "candidate_output": "Some candidate output",
            "available_evidence": "Evidence",
            "output_type": "text",
            "deterministic_checks": {}
        }
        result = engine.run(input_data)
        # Must fail-safely become HUMAN REVIEW, NEVER PASS
        self.assertEqual(result["decision"], "HUMAN REVIEW")
        self.assertIn("Invalid weighted score", result["reason"])


if __name__ == "__main__":
    unittest.main()
