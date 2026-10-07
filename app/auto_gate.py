"""Deterministic, source-grounded contract construction for the V0.2 Auto-Gate."""

import re
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple


_DURATION_PATTERN = re.compile(
    r"\b(?:(?:exactly|around|about|approximately)\s+)?"
    r"\d+\s*[- ]?\s*(?:seconds?|secs?)\b",
    re.IGNORECASE,
)
_ASPECT_PATTERN = re.compile(
    r"\bvertical\s+(\d{1,2}):(\d{1,2})\b",
    re.IGNORECASE,
)
_LANGUAGES = (
    "Arabic",
    "Bengali",
    "Chinese",
    "English",
    "French",
    "German",
    "Gujarati",
    "Hindi",
    "Japanese",
    "Kannada",
    "Marathi",
    "Portuguese",
    "Spanish",
    "Tamil",
    "Telugu",
    "Urdu",
)
_LANGUAGE_PATTERN = re.compile(
    r"\bin\s+(" + "|".join(_LANGUAGES) + r")\b",
    re.IGNORECASE,
)
_PROHIBITION_PATTERN = re.compile(
    r"\b(?:do\s+not|don['’]t|dont)\s+"
    r"(?:invent\s+[\w-]+\s+details|use\s+English)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_PATTERN = re.compile(r"\b(?:short|premium)\b", re.IGNORECASE)
_PREFERENCE_PATTERN = re.compile(
    r"\bI['’]d\s+prefer\s+something\s+elegant\b",
    re.IGNORECASE,
)
_INSTRUCTION_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:create|make|write|generate|produce|design)\b",
    re.IGNORECASE,
)
_NEGATED_CONTEXT = re.compile(
    r"\b(?:not|never|without|no|avoid|exclude|don't|dont|do\s+not|"
    r"doesn't|doesnt|didn't|didnt|can't|cannot|won't|wont|"
    r"shouldn't|shouldnt|wouldn't|wouldnt|isn't|isnt|aren't|arent|"
    r"wasn't|wasnt|weren't|werent|want\s+no)\b",
    re.IGNORECASE,
)
_METALINGUISTIC_CONTEXT = re.compile(
    r"\b(?:example|phrase|term|word|quote|quoted|mention(?:ed)?|say(?:s)?|"
    r"discuss(?:ed|ion)?|reference|refer(?:red)?\s+to)\b",
    re.IGNORECASE,
)
_QUOTED_SPAN_PATTERNS = (
    re.compile(r'"[^"\n]*"'),
    re.compile(r"(?<!\w)'[^'\n]+'(?!\w)"),
    re.compile(r"“[^”\n]*”"),
    re.compile(r"‘[^’\n]*’"),
    re.compile(r"`[^`\n]*`"),
)


def _record(
    request_text: str,
    start: int,
    end: int,
    authority: str,
    clarity: str,
) -> Dict[str, Any]:
    evidence = request_text[start:end]
    return {
        "requirement_text": evidence,
        "authority": authority,
        "source_span": {"start": start, "end": end},
        "source_evidence": evidence,
        "clarity": clarity,
        "eligible_for_lock": False,
    }


def _span_is_valid(request_text: str, record: Dict[str, Any]) -> bool:
    span = record.get("source_span")
    if not isinstance(span, dict):
        return False
    start, end = span.get("start"), span.get("end")
    return (
        type(start) is int
        and type(end) is int
        and 0 <= start < end <= len(request_text)
        and record.get("source_evidence") == request_text[start:end]
    )


def _duration_value(text: str) -> Optional[int]:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def _quoted_spans(request_text: str) -> List[Tuple[int, int]]:
    spans = [
        (match.start(), match.end())
        for pattern in _QUOTED_SPAN_PATTERNS
        for match in pattern.finditer(request_text)
    ]
    return sorted(spans)


def _has_instruction_context(
    request_text: str,
    start: int,
    end: int,
    quoted_spans: List[Tuple[int, int]],
    allow_prohibition: bool = False,
) -> bool:
    if any(start >= quote_start and end <= quote_end for quote_start, quote_end in quoted_spans):
        return False

    sentence_start = max(
        request_text.rfind(boundary, 0, start)
        for boundary in (".", "?", "!", "\n")
    ) + 1
    clause_start = max(
        request_text.rfind(boundary, 0, start)
        for boundary in (".", "?", "!", ";", "\n", ",")
    ) + 1
    sentence_prefix = request_text[sentence_start:start]
    prefix = request_text[clause_start:start]
    normalized_prefix = re.sub(r"^\s*(?:and|but)\s+", "", prefix, flags=re.IGNORECASE)
    if _NEGATED_CONTEXT.search(sentence_prefix) or _METALINGUISTIC_CONTEXT.search(
        sentence_prefix
    ):
        return False
    if _INSTRUCTION_PREFIX.match(normalized_prefix):
        return True
    return allow_prohibition and not normalized_prefix.strip()


def _extract(request_text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    found: List[Tuple[int, int, str, str, str, Any]] = []
    quoted_spans = _quoted_spans(request_text)

    for match in _DURATION_PATTERN.finditer(request_text):
        if _has_instruction_context(request_text, match.start(), match.end(), quoted_spans):
            found.append(
                (
                    match.start(),
                    match.end(),
                    "EXPLICIT_REQUIREMENT",
                    "CLEAR",
                    "duration",
                    _duration_value(match.group()),
                )
            )
    for match in _ASPECT_PATTERN.finditer(request_text):
        if _has_instruction_context(request_text, match.start(), match.end(), quoted_spans):
            numerator, denominator = int(match.group(1)), int(match.group(2))
            if numerator > 0 and denominator > 0:
                found.append(
                    (
                        match.start(),
                        match.end(),
                        "EXPLICIT_REQUIREMENT",
                        "CLEAR",
                        "aspect_ratio",
                        Fraction(numerator, denominator),
                    )
                )
            else:
                found.append(
                    (
                        match.start(),
                        match.end(),
                        "EXPLICIT_REQUIREMENT",
                        "UNSUPPORTED",
                        "aspect_ratio",
                        None,
                    )
                )
    for match in _LANGUAGE_PATTERN.finditer(request_text):
        if _has_instruction_context(request_text, match.start(), match.end(), quoted_spans):
            found.append(
                (
                    match.start(),
                    match.end(),
                    "EXPLICIT_REQUIREMENT",
                    "CLEAR",
                    "language",
                    match.group(1).casefold(),
                )
            )
    for match in _PROHIBITION_PATTERN.finditer(request_text):
        if _has_instruction_context(
            request_text,
            match.start(),
            match.end(),
            quoted_spans,
            allow_prohibition=True,
        ):
            found.append(
                (match.start(), match.end(), "EXPLICIT_REQUIREMENT", "CLEAR", "prohibition", None)
            )
    for match in _AMBIGUOUS_PATTERN.finditer(request_text):
        if _has_instruction_context(request_text, match.start(), match.end(), quoted_spans):
            found.append(
                (match.start(), match.end(), "EXPLICIT_REQUIREMENT", "AMBIGUOUS", "ambiguous", None)
            )
    for match in _PREFERENCE_PATTERN.finditer(request_text):
        if not any(
            match.start() >= quote_start and match.end() <= quote_end
            for quote_start, quote_end in quoted_spans
        ):
            found.append(
                (match.start(), match.end(), "INFERRED_PREFERENCE", "AMBIGUOUS", "preference", None)
            )

    found.sort(key=lambda item: (item[0], item[1], item[4]))
    records = [
        _record(request_text, start, end, authority, clarity)
        for start, end, authority, clarity, _, _ in found
    ]

    issues: List[str] = []
    for constraint_type in ("duration", "aspect_ratio", "language"):
        values = {
            value
            for _, _, authority, clarity, kind, value in found
            if kind == constraint_type
            and authority == "EXPLICIT_REQUIREMENT"
            and clarity == "CLEAR"
            and value is not None
        }
        if len(values) > 1:
            for index, (_, _, authority, clarity, kind, value) in enumerate(found):
                if (
                    kind == constraint_type
                    and authority == "EXPLICIT_REQUIREMENT"
                    and clarity == "CLEAR"
                    and value is not None
                ):
                    records[index]["clarity"] = "CONFLICTING"
            issues.append(f"Conflicting explicit {constraint_type.replace('_', ' ')} constraints.")

    for record in records:
        record["eligible_for_lock"] = (
            record["authority"] == "EXPLICIT_REQUIREMENT"
            and record["clarity"] == "CLEAR"
            and _span_is_valid(request_text, record)
        )
        if record["authority"] == "EXPLICIT_REQUIREMENT" and record["clarity"] == "AMBIGUOUS":
            issues.append(f"Ambiguous explicit constraint: {record['source_evidence']}")
        elif record["authority"] == "EXPLICIT_REQUIREMENT" and record["clarity"] == "UNSUPPORTED":
            issues.append(f"Unsupported explicit constraint: {record['source_evidence']}")

    return records, issues


def build_contract(request_text: str) -> Dict[str, Any]:
    """Build a contract without inferring or fabricating requirements."""
    if not isinstance(request_text, str) or not request_text.strip():
        raise ValueError("request_text must be a nonempty string")

    requirements, issues = _extract(request_text)
    locked_requirements = [
        record["requirement_text"]
        for record in requirements
        if record["eligible_for_lock"]
    ]
    if not locked_requirements:
        issues.append("No safely extractable explicit requirement was found.")

    provenance_valid = all(_span_is_valid(request_text, record) for record in requirements)
    if not provenance_valid:
        issues.append("Requirement source provenance could not be verified.")

    status = (
        "READY"
        if locked_requirements and not issues and provenance_valid
        else "NEEDS_CLARIFICATION"
    )
    return {
        "original_request": request_text,
        "requirements": requirements,
        "locked_requirements": locked_requirements,
        "clarification_issues": issues,
        "status": status,
    }


def canonical_payload(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Return a payload only if caller-provided state exactly matches reconstruction."""
    if not isinstance(contract, dict):
        raise ValueError("Auto-Gate contract is not ready for evaluation.")

    request_text = contract.get("original_request")
    try:
        expected = build_contract(request_text)
    except (TypeError, ValueError):
        raise ValueError("Auto-Gate contract is invalid.") from None

    if not _same_contract_state(contract, expected):
        raise ValueError("Auto-Gate contract does not match deterministic reconstruction.")
    if expected["status"] != "READY":
        raise ValueError("Auto-Gate contract is not ready for evaluation.")

    return {
        "original_request": expected["original_request"],
        "locked_requirements": expected["locked_requirements"],
        "output_type": "text",
    }


def _same_contract_state(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return (
            actual.keys() == expected.keys()
            and all(_same_contract_state(actual[key], expected[key]) for key in expected)
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_contract_state(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected
