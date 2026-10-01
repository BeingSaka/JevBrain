import hashlib
import json
import time
import uuid
from .normalize import normalize, deterministic, EngineError
from .policy import decide, validate_thresholds
from .repair import repair_payload
from .jev_client import validate_response
from .failure_rules import validate_rules, applicable, questions_for, findings_for

MAX_REPAIRS = 2

class Engine:
    def __init__(self, evaluator, worker, profile, thresholds, logger, rules=None):
        self.evaluator, self.worker, self.profile = evaluator, worker, profile
        self.thresholds, self.logger = validate_thresholds(thresholds), logger
        self.rules = validate_rules(rules if rules is not None else [], profile)
    def run(self, data):
        run_id, history, repairs, seen = str(uuid.uuid4()), [], 0, set()
        state, checks = normalize(data)
        candidate = state["candidate_output"]
        rule_findings, previous_triggered, repaired_from = [], set(), []
        repair_performed = False
        worker_calls = []
        def call_worker(operation, payload):
            start = time.monotonic()
            call = {"operation": operation, "attempt": repairs, "status": "error"}
            try:
                method = getattr(self.worker, operation, None)
                output = method(payload) if callable(method) else self.worker.run(payload)
                if not isinstance(output, str) or not output.strip():
                    raise EngineError("Worker returned empty/non-text output")
                call["status"] = "success"
                return output
            finally:
                usage = getattr(self.worker, "last_usage", None)
                call["usage"] = {k:v for k,v in usage.items() if type(v) is int and v >= 0} if isinstance(usage,dict) else None
                call["elapsed_seconds"] = time.monotonic()-start
                worker_calls.append(call)
        def record(decision, failed, primary, reason, result=None, elapsed=0):
            event = {"run_id": run_id, "task_type": state["output_type"],
                     "worker": getattr(self.worker, "name", "none"),
                     "worker_calls": list(worker_calls),
                     "evaluation_profile": self.profile["name"],
                     "profile_sha256": hashlib.sha256(json.dumps(self.profile, sort_keys=True).encode()).hexdigest(),
                     "thresholds": self.thresholds, "candidate_sha256": hashlib.sha256((state["candidate_output"] or "").encode()).hexdigest(),
                     "state_sha256": hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest(),
                     "jev_results": result, "policy_decision": decision,
                     "rule_library_sha256": hashlib.sha256(json.dumps(self.rules, sort_keys=True).encode()).hexdigest(),
                     "rule_findings": rule_findings,
                     "triggered_rule_ids": [r["rule_id"] for r in rule_findings if r["status"] == "triggered"],
                     "repair_performed": repair_performed,
                     "repaired_from_rule_ids": repaired_from,
                     "repair_requested": decision == "REVISE",
                     "retry_count": repairs, "primary_failure": primary,
                     "failed_dimensions": failed, "reason": reason, "elapsed_seconds": elapsed,
                     "evaluator": getattr(self.evaluator, "name", "unknown"),
                     "estimated_jev_usd": result["usage"]["input_tokens"]*.042/1_000_000 if result and getattr(self.evaluator, "name", "") == "typesafe-http" else None}
            self.logger.write(event); history.append(event)
        def final(decision, reason):
            return {"run_id": run_id, "decision": decision, "reason": reason,
                    "final_output": state["candidate_output"], "repairs": repairs, "worker_calls": worker_calls, "history": history}
        try:
            if candidate is None:
                if self.worker is None: raise EngineError("Generation requires a configured worker")
                candidate = call_worker("generate", {"original_request": state["original_request"],
                    "locked_requirements": state["locked_requirements"],
                    "known_constraints": state["known_constraints"],
                    "available_evidence": state["available_evidence"], "output_type": state["output_type"],
                    "deterministic_constraints": checks,
                    **{k:state[k] for k in ("previous_candidate", "allowed_changes") if k in state}})
                state["candidate_output"] = candidate
            while True:
                if not isinstance(candidate, str): raise EngineError("Worker output must be text")
                rule_findings = []
                if candidate in seen:
                    record("HUMAN REVIEW", [], "other", "Worker returned an unchanged or previously evaluated candidate")
                    return final("HUMAN REVIEW", history[-1]["reason"])
                seen.add(candidate)
                active = applicable(self.rules, state, checks)
                failed = deterministic(candidate, checks)
                rule_findings = findings_for(active, failed, None, self.thresholds, previous_triggered)
                if failed:
                    decision, primary, reason, result = "REVISE", "format_violation", "Deterministic validation failed", None
                else:
                    start = time.monotonic()
                    questions = questions_for(self.profile, active)
                    evaluation_state = dict(state)
                    if self.rules:
                        evaluation_state["deterministic_check_results"] = {"failed":failed, "configured":checks}
                    result = validate_response(self.evaluator.evaluate(evaluation_state, questions), questions)
                    rule_findings = findings_for(active, failed, result, self.thresholds, previous_triggered)
                    decision, failed, reason = decide(result, self.thresholds, rule_findings)
                    primary = result["answers"]["primary_failure"]["choice"]
                if decision == "REVISE" and (repairs >= MAX_REPAIRS or self.worker is None):
                    decision = "HUMAN REVIEW"
                    reason = "Two-repair limit reached" if repairs >= MAX_REPAIRS else "Repair requires a configured worker"
                record(decision, failed, primary, reason, result, time.monotonic()-start if result else 0)
                if decision != "REVISE": return final(decision, reason)
                payload = repair_payload(state, failed, primary, checks, rule_findings)
                previous_triggered |= {r["rule_id"] for r in rule_findings if r["status"] == "triggered"}
                repaired_from = [r["rule_id"] for r in rule_findings if r["status"] == "triggered" and r["severity"] != "INFO"]
                repair_performed = False
                repairs += 1
                corrected = call_worker("repair", payload)
                if self.rules:
                    state["previous_candidate"] = candidate
                    state["repair_context"] = {"failed_dimensions": failed, "failure_rules": payload["failure_rules"],
                                              "required_correction": payload["required_correction"]}
                    state.pop("allowed_changes", None)  # Original permission is not renewed for later repairs.
                candidate = corrected
                state["candidate_output"] = candidate
                repair_performed = True
        except EngineError as e:
            record("HUMAN REVIEW", [], "other", str(e))
            return final("HUMAN REVIEW", str(e))
