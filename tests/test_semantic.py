import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from jev_engine.engine import Engine
from jev_engine.semantic import (
    extract_semantic_evaluation,
    validate_semantic_evaluation,
    semantic_decide,
    CHOICE_ENUM,
)
from jev_engine.logging import JsonlLogger
from jev_engine.normalize import EngineError
from jev_engine.failure_rules import load_packs

PROFILE = json.loads((ROOT / 'evaluators/universal.json').read_text())
THRESHOLDS = json.loads((ROOT / 'config/thresholds.json').read_text())
RULES = load_packs([str(ROOT / 'rules/universal.json')], PROFILE)
INPUT = json.loads((ROOT / 'examples/input.json').read_text())


import math

def make_response(questions=None, good=True, choice="none", score=4.0, noul=0.98, confidence=0.95, violations=None, noul_conf=None, choice_conf=None, score_conf=None):
    """Constructs a valid single-batched Jev evaluation response matching questions."""
    q_dict = dict(questions or PROFILE['questions'])
    violations = set(violations or [])
    answers = {}
    for k, q in q_dict.items():
        if q['type'] == 'noul':
            if k.startswith('failure_'):
                rid = k.removeprefix('failure_')
                answers[k] = {'type': 'noul', 'noul': 0.95 if rid in violations else 0.02}
            else:
                positive = k in ('requirements_met', 'evidence_sufficient', 'ready_to_deliver')
                if good:
                    val = noul if positive else 0.02
                else:
                    val = 0.02 if positive else noul
                ans_obj = {'type': 'noul', 'noul': val}
                ans_obj['confidence'] = noul_conf if noul_conf is not None else confidence
                answers[k] = ans_obj

    c_conf = choice_conf if choice_conf is not None else confidence
    choice_val = choice if not good else 'none'
    answers['primary_failure'] = {
        'type': 'choice',
        'choice': choice_val,
        'confidence': c_conf,
        'probabilities': {k: (1.0 if k == choice_val else 0.0) for k in q_dict['primary_failure']['criteria']},
    }

    s_conf = score_conf if score_conf is not None else confidence
    score_val = float(score if good else min(score, 1.5))
    i = int(math.floor(score_val))
    probs = {str(k): 0.0 for k in range(5)}
    if i >= 4:
        probs["4"] = 1.0
    else:
        probs[str(i)] = round((i + 1) - score_val, 4)
        probs[str(i + 1)] = round(score_val - i, 4)
    diff = 1.0 - sum(probs.values())
    probs[str(min(4, i + 1))] = round(probs[str(min(4, i + 1))] + diff, 4)

    answers['production_readiness'] = {
        'type': 'score',
        'score': score_val,
        'confidence': s_conf,
        'probabilities': probs,
        'legend': {str(i): v for i, v in enumerate(q_dict['production_readiness']['criteria'])},
    }
    return {
        'model': 'jev-1.13.0',
        'answers': answers,
        'usage': {'input_tokens': 1200, 'output_tokens': 80},
    }

class Evaluator:
    name = 'fixture-semantic-evaluator'
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
    def evaluate(self, state, questions):
        self.calls += 1
        val = self.responses.pop(0)
        if isinstance(val, Exception):
            raise val
        if callable(val):
            val = val(questions)
        elif isinstance(val, dict) and isinstance(val.get("answers"), dict):
            missing = set(questions) - set(val["answers"])
            if missing:
                full = make_response(questions, good=True)
                for m in missing:
                    val["answers"][m] = full["answers"][m]
        return copy.deepcopy(val)


class Worker:
    name = 'fixture-semantic-worker'
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.payloads = []
    def run(self, payload):
        self.payloads.append(payload)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class SemanticEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = JsonlLogger(Path(self.tmp.name) / 'events.jsonl')

    def engine(self, e, w=None, rules=None, enabled=True):
        return Engine(
            e,
            w,
            PROFILE,
            THRESHOLDS,
            self.log,
            rules=rules or [],
            semantic_evaluation_enabled=enabled,
        )

    # -------------------------------------------------------------
    # 1. PASS — Candidate satisfies all requirements
    # -------------------------------------------------------------
    def test_pass(self):
        e = Evaluator([make_response(good=True, choice="none", score=4.0, noul=0.98)])
        engine = self.engine(e)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'PASS')
        self.assertIn('semantic_evaluation', result)
        sem = result['semantic_evaluation']
        self.assertEqual(sem['choice']['value'], 'none')
        self.assertGreaterEqual(sem['score']['value'], THRESHOLDS['score_min'])
        self.assertGreaterEqual(sem['noul']['value'], THRESHOLDS['accept_min'])
        self.assertEqual(result['repairs'], 0)

    # -------------------------------------------------------------
    # 2. Critical deterministic violation — PASS prohibited
    # -------------------------------------------------------------
    def test_critical_deterministic_violation(self):
        e = Evaluator([make_response(good=True, score=4.0, noul=0.99)])
        w = Worker(['Repaired candidate with MANDATORY_PHRASE_ABSENT'])
        data = copy.deepcopy(INPUT)
        data['deterministic_checks'] = {'required_substrings': ['MANDATORY_PHRASE_ABSENT']}
        engine = self.engine(e, w)
        result = engine.run(data)
        # First step deterministic failed; cannot PASS. Worker repaired it, then second step evaluated.
        self.assertNotEqual(result['history'][0]['policy_decision'], 'PASS')
        self.assertEqual(result['history'][0]['policy_decision'], 'REPAIR')
        self.assertEqual(result['decision'], 'PASS')
        self.assertEqual(result['repairs'], 1)

    # -------------------------------------------------------------
    # 3. Unsupported claim — choice = unsupported_claim
    # -------------------------------------------------------------
    def test_unsupported_claim(self):
        bad = make_response(good=False, choice="unsupported_claim", score=1.0, noul=0.3)
        good = make_response(good=True, choice="none", score=4.0, noul=0.96)
        e = Evaluator([bad, good])
        w = Worker(['Atlas launches on 15 October 2026. Price has not been announced.'])
        engine = self.engine(e, w)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'PASS')
        self.assertEqual(result['repairs'], 1)
        first_event = result['history'][0]
        self.assertEqual(first_event['policy_decision'], 'REPAIR')
        self.assertEqual(first_event['semantic_evaluation']['choice']['value'], 'unsupported_claim')
        self.assertEqual(w.payloads[0]['primary_failure'], 'unsupported_claim')
        self.assertTrue(any(t['type'] == 'unsupported_claim' for t in w.payloads[0].get('repair_targets', [])))

    # -------------------------------------------------------------
    # 4. Missing requirement — choice = missing_requirement
    # -------------------------------------------------------------
    def test_missing_requirement(self):
        bad = make_response(good=False, choice="missing_requirement", score=1.0, noul=0.2)
        good = make_response(good=True, choice="none", score=4.0, noul=0.95)
        e = Evaluator([bad, good])
        w = Worker(['Atlas launch date on 15 October 2026 fully restored.'])
        engine = self.engine(e, w)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'PASS')
        self.assertEqual(result['repairs'], 1)
        first_sem = result['history'][0]['semantic_evaluation']
        self.assertEqual(first_sem['choice']['value'], 'missing_requirement')

    # -------------------------------------------------------------
    # 5. Low semantic confidence — HUMAN REVIEW
    # -------------------------------------------------------------
    def test_low_semantic_confidence(self):
        # Confidence is 0.40, which is below confidence_min 0.65
        resp = make_response(good=True, score=4.0, noul=0.95, confidence=0.40)
        e = Evaluator([resp])
        engine = self.engine(e)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'HUMAN REVIEW')
        self.assertEqual(result['reason'], 'Low semantic confidence')

    # -------------------------------------------------------------
    # 5b. PART B Regression: Noul confidence alone triggers HUMAN REVIEW
    # -------------------------------------------------------------
    def test_noul_confidence_gate(self):
        # noul.value high enough for PASS (0.98 >= 0.90)
        # score.value high enough for PASS (4.0 >= 3.5)
        # choice = none
        # noul.confidence < confidence_min (0.40 < 0.65)
        # choice.confidence >= confidence_min (0.95 >= 0.65)
        # score.confidence >= confidence_min (0.95 >= 0.65)
        resp = make_response(
            good=True,
            choice="none",
            score=4.0,
            noul=0.98,
            noul_conf=0.40,
            choice_conf=0.95,
            score_conf=0.95,
        )
        e = Evaluator([resp])
        engine = self.engine(e)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'HUMAN REVIEW')
        self.assertEqual(result['reason'], 'Low semantic confidence')
        self.assertEqual(result['semantic_evaluation']['noul']['confidence'], 0.40)
        self.assertEqual(result['semantic_evaluation']['choice']['confidence'], 0.95)
        self.assertEqual(result['semantic_evaluation']['score']['confidence'], 0.95)

    # -------------------------------------------------------------
    # 6. High Score + Critical Failure (score=4.0, noul=0.99, FR002 triggered) -> NOT PASS
    # -------------------------------------------------------------
    def test_high_score_with_critical_failure(self):
        resp_fn = lambda q: make_response(q, good=True, score=4.0, noul=0.99, confidence=0.98, violations=['FR002'])
        e = Evaluator([resp_fn])
        # Worker is None; since repair is needed but no worker, engine must stop at HUMAN REVIEW
        engine = self.engine(e, w=None, rules=RULES)
        result = engine.run(INPUT)
        self.assertNotEqual(result['decision'], 'PASS')
        self.assertEqual(result['decision'], 'HUMAN REVIEW')
        # Check that in history, policy decision recognized the critical rule
        self.assertIn('rule:FR002', result['history'][0]['failed_dimensions'])

    # -------------------------------------------------------------
    # 7. Invalid semantic JSON / Malformed response -> NOT PASS
    # -------------------------------------------------------------
    def test_invalid_semantic_json(self):
        e = Evaluator([{'model': 'jev-1.13.0', 'answers': 'not a dictionary', 'usage': {}}])
        engine = self.engine(e)
        result = engine.run(INPUT)
        self.assertNotEqual(result['decision'], 'PASS')
        self.assertEqual(result['decision'], 'HUMAN REVIEW')

    # -------------------------------------------------------------
    # 8. Worker timeout / failure -> NOT PASS
    # -------------------------------------------------------------
    def test_worker_failure(self):
        bad = make_response(good=False, choice="unsupported_claim", score=1.5, noul=0.2)
        e = Evaluator([bad])
        w = Worker([TimeoutError("Worker timed out")])
        engine = self.engine(e, w)
        result = engine.run(INPUT)
        self.assertNotEqual(result['decision'], 'PASS')
        self.assertEqual(result['decision'], 'HUMAN REVIEW')

    # -------------------------------------------------------------
    # 8b. Evaluator exception -> NOT PASS (routes to HUMAN REVIEW)
    # -------------------------------------------------------------
    def test_evaluator_exception(self):
        e = Evaluator([RuntimeError("Evaluator process crashed")])
        engine = self.engine(e)
        result = engine.run(INPUT)
        self.assertNotEqual(result['decision'], 'PASS')
        self.assertEqual(result['decision'], 'HUMAN REVIEW')
        self.assertIn('Evaluator execution failure', result['reason'])

    # -------------------------------------------------------------
    # 9. Retry semantics: initial -> repair 1 -> eval -> repair 2 -> eval -> HUMAN REVIEW
    # -------------------------------------------------------------
    def test_retry_exhaustion(self):
        bad1 = make_response(good=False, choice="unsupported_claim", score=1.0, noul=0.2)
        bad2 = make_response(good=False, choice="unsupported_claim", score=1.0, noul=0.3)
        bad3 = make_response(good=False, choice="unsupported_claim", score=1.0, noul=0.4)
        e = Evaluator([bad1, bad2, bad3])
        w = Worker(['revision attempt 1', 'revision attempt 2'])
        engine = self.engine(e, w)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'HUMAN REVIEW')
        self.assertEqual(result['repairs'], 2)
        self.assertIn('Two-repair limit reached', result['reason'])
        # Exactly 3 evaluation calls: initial, after repair 1, after repair 2
        self.assertEqual(e.calls, 3)
        # Exactly 2 worker repair calls
        self.assertEqual(len(w.payloads), 2)

    # -------------------------------------------------------------
    # 9b. Targeted repair propagation to worker
    # -------------------------------------------------------------
    def test_targeted_repair_propagation(self):
        bad = make_response(good=False, choice="unsupported_claim", score=1.0, noul=0.3)
        good = make_response(good=True, choice="none", score=4.0, noul=0.98)
        e = Evaluator([bad, good])
        w = Worker(['Corrected claim according to target instructions.'])
        engine = self.engine(e, w)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'PASS')
        self.assertEqual(len(w.payloads), 1)
        payload = w.payloads[0]
        # Prove worker genuinely received repair_targets
        self.assertIn('repair_targets', payload)
        self.assertTrue(len(payload['repair_targets']) > 0)
        self.assertTrue(any(t['type'] == 'unsupported_claim' for t in payload['repair_targets']))
        # Prove worker also received targeted instruction in required_correction actions
        self.assertIn('required_correction', payload)
        actions = payload['required_correction']['actions']
        self.assertTrue(any('unsupported_claim' in a for a in actions))

    # -------------------------------------------------------------
    # 10. Backward compatibility — Semantic layer disabled
    # -------------------------------------------------------------
    def test_backward_compatibility_disabled(self):
        e = Evaluator([make_response(good=True, score=4.0, noul=0.98)])
        # When semantic_evaluation_enabled is False, behavior is exactly legacy V1/V2
        engine = self.engine(e, enabled=False)
        result = engine.run(INPUT)
        self.assertEqual(result['decision'], 'PASS')
        # In legacy mode, semantic_evaluation is not injected
        self.assertNotIn('semantic_evaluation', result)

    # -------------------------------------------------------------
    # 11. Schema & Validation Checks
    # -------------------------------------------------------------
    def test_semantic_schema_validation(self):
        # Valid schema
        valid_obj = {
            "noul": {"value": 0.92, "confidence": 0.90, "reason": "ok"},
            "choice": {"value": "none", "confidence": 0.95, "reason": "no error"},
            "score": {"value": 3.8, "confidence": 0.91, "reason": "production ready"},
            "concerns": [],
            "repair_targets": [{"type": "format", "location": "header", "instruction": "fix title"}],
        }
        self.assertEqual(validate_semantic_evaluation(valid_obj), valid_obj)

        # Invalid choice enum
        bad_choice = copy.deepcopy(valid_obj)
        bad_choice["choice"]["value"] = "invalid_category"
        with self.assertRaises(EngineError):
            validate_semantic_evaluation(bad_choice)

        # Score out of range (> 4.0)
        bad_score = copy.deepcopy(valid_obj)
        bad_score["score"]["value"] = 4.5
        with self.assertRaises(EngineError):
            validate_semantic_evaluation(bad_score)

        # Noul out of range (> 1.0)
        bad_noul = copy.deepcopy(valid_obj)
        bad_noul["noul"]["value"] = 1.2
        with self.assertRaises(EngineError):
            validate_semantic_evaluation(bad_noul)

    # -------------------------------------------------------------
    # 11b. Safe failure validation (Part C.2: NaN, Infinity, types, ranges)
    # -------------------------------------------------------------
    def test_safe_failure_nan_and_infinity(self):
        base = {
            "noul": {"value": 0.95, "confidence": 0.90, "reason": "ok"},
            "choice": {"value": "none", "confidence": 0.95, "reason": "none"},
            "score": {"value": 4.0, "confidence": 0.95, "reason": "ready"},
            "concerns": ["concern 1"],
            "repair_targets": [{"type": "t", "location": "l", "instruction": "i"}],
        }
        # NaN and Infinity checks
        for bad_val in (float("nan"), float("inf"), float("-inf")):
            # noul value
            d = copy.deepcopy(base); d["noul"]["value"] = bad_val
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)
            # noul confidence
            d = copy.deepcopy(base); d["noul"]["confidence"] = bad_val
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)
            # choice confidence
            d = copy.deepcopy(base); d["choice"]["confidence"] = bad_val
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)
            # score value
            d = copy.deepcopy(base); d["score"]["value"] = bad_val
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)
            # score confidence
            d = copy.deepcopy(base); d["score"]["confidence"] = bad_val
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)

    def test_safe_failure_ranges_and_types(self):
        base = {
            "noul": {"value": 0.95, "confidence": 0.90, "reason": "ok"},
            "choice": {"value": "none", "confidence": 0.95, "reason": "none"},
            "score": {"value": 4.0, "confidence": 0.95, "reason": "ready"},
            "concerns": ["concern 1"],
            "repair_targets": [{"type": "t", "location": "l", "instruction": "i"}],
        }
        # Out-of-range checks
        for field, key, bad in [
            ("noul", "value", -0.1), ("noul", "value", 1.1),
            ("noul", "confidence", -0.05), ("noul", "confidence", 1.05),
            ("choice", "confidence", -0.01), ("choice", "confidence", 1.01),
            ("score", "value", -0.5), ("score", "value", 4.1),
            ("score", "confidence", -0.1), ("score", "confidence", 1.1),
        ]:
            d = copy.deepcopy(base); d[field][key] = bad
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)

        # Missing required fields
        for req in ("noul", "choice", "score", "concerns", "repair_targets"):
            d = copy.deepcopy(base); del d[req]
            with self.assertRaises(EngineError): validate_semantic_evaluation(d)

        # Non-string reason
        d = copy.deepcopy(base); d["noul"]["reason"] = 123
        with self.assertRaises(EngineError): validate_semantic_evaluation(d)

        # Malformed concerns
        d = copy.deepcopy(base); d["concerns"] = [123]
        with self.assertRaises(EngineError): validate_semantic_evaluation(d)
        d = copy.deepcopy(base); d["concerns"] = "not a list"
        with self.assertRaises(EngineError): validate_semantic_evaluation(d)

        # Malformed repair_targets
        d = copy.deepcopy(base); d["repair_targets"] = "not a list"
        with self.assertRaises(EngineError): validate_semantic_evaluation(d)
        d = copy.deepcopy(base); d["repair_targets"] = [{"type": "a", "location": "b", "instruction": ""}]
        with self.assertRaises(EngineError): validate_semantic_evaluation(d)

    # -------------------------------------------------------------
    # 12. Observability Fields Preserved (Section 18)
    # -------------------------------------------------------------
    def test_observability_fields(self):
        e = Evaluator([make_response(good=True, score=4.0, noul=0.98)])
        engine = self.engine(e)
        result = engine.run(INPUT)
        event = result['history'][0]
        self.assertIn('evaluation_latency_ms', event)
        self.assertGreaterEqual(event['evaluation_latency_ms'], 0)
        # Cost is None when not measured / non-typesafe-http evaluator, never fabricated 0.0
        self.assertIn('evaluation_cost_usd', event)
        self.assertIsNone(event['evaluation_cost_usd'])
        self.assertIn('checks_performed', event)
        self.assertGreater(event['checks_performed'], 0)
        self.assertIn('rules_triggered', event)
        self.assertIsInstance(event['rules_triggered'], list)
        self.assertIn('repair_count', event)
        self.assertEqual(event['repair_count'], 0)
        self.assertIn('semantic_evaluation', event)
        self.assertIn('noul', event['semantic_evaluation'])


if __name__ == '__main__':
    unittest.main()
