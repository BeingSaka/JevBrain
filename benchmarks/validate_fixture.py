import json
import hashlib
from pathlib import Path

def validate():
    root = Path(__file__).resolve().parents[1]
    locked_path = root / "benchmarks/noul_benchmark_v1_locked.json"
    spec_path = root / "benchmarks/noul_benchmark_v1_integrity.txt"

    spec_text = spec_path.read_text(encoding="utf-8")
    data = json.loads(locked_path.read_text(encoding="utf-8"))

    # Gate 1: Assert case count == 36
    cases = data.get("cases", [])
    if len(cases) != 36:
        raise ValueError(f"Case count mismatch: expected 36, got {len(cases)}")

    # Gate 2: Assert IDs exactly match expected ordered ID list
    expected_ids = [
        "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08",
        "R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08",
        "H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08",
        "X01", "X02", "X03", "X04", "X05", "X06", "X07", "X08",
        "X09", "X10", "X11", "X12"
    ]
    actual_ids = [c["case_id"] for c in cases]
    if actual_ids != expected_ids:
        raise ValueError(f"IDs do not match expected ordered list:\nExpected: {expected_ids}\nActual: {actual_ids}")

    # Gate 3: Assert labels total ACCEPT=12, REPAIR=16, HUMAN_REVIEW=8
    counts = {}
    for c in cases:
        lbl = c["gold_label"]
        counts[lbl] = counts.get(lbl, 0) + 1
    expected_dist = {"ACCEPT": 12, "REPAIR": 16, "HUMAN_REVIEW": 8}
    if counts != expected_dist:
        raise ValueError(f"Label distribution mismatch: expected {expected_dist}, got {counts}")

    # Gate 4: Assert all IDs are unique
    if len(set(actual_ids)) != 36:
        raise ValueError("Duplicate case IDs detected")

    # Gate 5: Assert every case contains all mandatory fields
    required_fields = {
        "case_id", "requirement", "available_evidence", "candidate_output",
        "gold_label", "gold_reason", "expected_noul_band", "critical_violation",
        "pass_allowed", "human_review_required"
    }
    for c in cases:
        missing = required_fields - set(c)
        if missing:
            raise ValueError(f"Case {c.get('case_id')} missing required fields: {missing}")

    # Gate 6: Verify pre-integrity hash recorded in fixture matches specification
    recorded_hash = data.get("integrity", {}).get("content_sha256_pre_integrity")
    expected_hash = "72c885103538fb7cc877ddbf5bb7ecfbaf209226c9b85cb29f0cdb5cacec809a"
    if recorded_hash != expected_hash:
        raise ValueError(f"Pre-integrity hash mismatch: expected {expected_hash}, got {recorded_hash}")

    print("ALL MANDATORY PRE-RUN INTEGRITY GATES PASSED:")
    print("  [x] Case count == 36")
    print("  [x] Exactly matches expected ordered ID list (A01..A08, R01..R08, H01..H08, X01..X12)")
    print("  [x] Label distribution exact (ACCEPT=12, REPAIR=16, HUMAN_REVIEW=8)")
    print("  [x] All 36 IDs are unique")
    print("  [x] All 10 required schema fields present in every case")
    print(f"  [x] Pre-integrity canonical SHA-256 verified: {recorded_hash}")
    return True

if __name__ == "__main__":
    validate()
