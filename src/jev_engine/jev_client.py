import json
import math
import os
import time
import urllib.request
import urllib.error
from .normalize import EngineError

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def post_json(url, payload, key=None, timeout=30, attempts=1):
    headers = {"Content-Type": "application/json"}
    if key: headers["Authorization"] = "Bearer " + key
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as r:
                body = r.read(2_000_001)
                if len(body) > 2_000_000: raise EngineError("Provider response exceeds size limit")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and attempt + 1 < attempts:
                try: delay = float(e.headers.get("Retry-After", 2 ** attempt))
                except ValueError: delay = 2 ** attempt
                if not math.isfinite(delay) or delay > 10:
                    raise EngineError("Provider requests a later retry") from None
                time.sleep(max(0, delay)); continue
            raise EngineError(f"Provider HTTP {e.code}; no response body logged") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EngineError("Provider connection/timeout failure; not retried to avoid duplicate billing") from None
        except (ValueError, UnicodeError):
            raise EngineError("Provider returned invalid JSON") from None

def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise EngineError("Invalid numeric evaluation result")

def validate_response(response, questions):
    if not isinstance(response, dict) or not isinstance(response.get("model"), str):
        raise EngineError("Invalid evaluation response")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise EngineError("Evaluation answers missing or unexpected")
    for key, q in questions.items():
        a = answers[key]
        if not isinstance(a, dict) or a.get("type") != q["type"]:
            raise EngineError("Evaluation type mismatch")
        if q["type"] == "noul": number(a.get("noul"), 0, 1); continue
        number(a.get("confidence"), 0, 1)
        expected = set(q["criteria"]) if q["type"] == "choice" else {str(i) for i in range(len(q["criteria"]))}
        probs = a.get("probabilities")
        if not isinstance(probs, dict) or set(probs) != expected:
            raise EngineError("Invalid evaluation distribution")
        for v in probs.values(): number(v, 0, 1)
        prob_sum = sum(probs.values())
        if abs(prob_sum - 1) > .01: raise EngineError("Evaluation probabilities do not sum to one")
        if q["type"] == "choice":
            if a.get("choice") not in expected or probs[a["choice"]] + .001 < max(probs.values()):
                raise EngineError("Invalid winning choice")
        else:
            number(a.get("score"), 0, len(expected)-1)
            weighted = sum(int(k) * v for k, v in probs.items()) / prob_sum
            if abs(a["score"] - weighted) > .05 + 1e-9:
                raise EngineError("Invalid weighted score")
            if not isinstance(a.get("legend"), dict) or set(a["legend"]) != expected:
                raise EngineError("Score legend missing")
    usage = response.get("usage")
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
        raise EngineError("Invalid token usage")
    return response

class JevClient:
    name = "typesafe-http"
    def __init__(self, model=None):
        self.model = model or os.environ.get("JEV_MODEL", "jev-1.13.0")
    def evaluate(self, state, questions):
        key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not key: raise EngineError("TYPESAFE_API_KEY is not configured")
        payload = {"model": self.model, "state": state, "questions": questions}
        # Conservative UTF-8 byte guards; no unsafe truncation or invented tokenizer.
        state_bytes = len(json.dumps(state, ensure_ascii=False).encode())
        longest = max(len(json.dumps(q, ensure_ascii=False).encode()) for q in questions.values())
        if state_bytes + longest > 30_000 or len(json.dumps(payload, ensure_ascii=False).encode()) > 60_000:
            raise EngineError("Input exceeds conservative local context guard; shorten explicitly")
        return validate_response(post_json("https://api.typesafe.ai/v1/systemone", payload, key, attempts=3), questions)
