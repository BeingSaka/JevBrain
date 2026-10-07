import subprocess
import unittest
from copy import deepcopy
from pathlib import Path

from app.auto_gate import build_contract, canonical_payload


ROOT = Path(__file__).resolve().parents[2]
FROZEN_BASE = "14752c7bc7c97267113fee1e1375e665d6d60b22"


class AutoGateTests(unittest.TestCase):
    def test_preserves_original_request_exactly(self):
        request = "  Make a reel in Marathi. \n"
        contract = build_contract(request)
        self.assertEqual(contract["original_request"], request)

    def test_extracts_clear_explicit_patterns_as_locks(self):
        request = "Create a 10-second vertical 9:16 reel in Marathi."
        contract = build_contract(request)
        self.assertEqual(contract["status"], "READY")
        self.assertEqual(
            contract["locked_requirements"],
            ["10-second", "vertical 9:16", "in Marathi"],
        )

    def test_prohibitions_are_clear_explicit_locks(self):
        for request, expected in (
            ("Do not invent saree details.", "Do not invent saree details"),
            ("Don't use English.", "Don't use English"),
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertEqual(contract["status"], "READY")
                self.assertEqual(contract["locked_requirements"], [expected])

    def test_source_spans_reproduce_evidence_and_text(self):
        request = "Please create a 10-second reel in Marathi."
        contract = build_contract(request)
        for record in contract["requirements"]:
            start = record["source_span"]["start"]
            end = record["source_span"]["end"]
            self.assertEqual(record["source_evidence"], request[start:end])
            self.assertEqual(record["requirement_text"], record["source_evidence"])

    def test_does_not_invent_requirements(self):
        request = "Create a Maheshwari saree reel."
        contract = build_contract(request)
        self.assertEqual(contract["requirements"], [])
        self.assertEqual(contract["locked_requirements"], [])
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")

    def test_ambiguous_explicit_constraints_need_clarification(self):
        contract = build_contract("Make it short and premium.")
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(contract["locked_requirements"], [])
        self.assertTrue(all(not item["eligible_for_lock"] for item in contract["requirements"]))
        self.assertTrue(all(item["clarity"] == "AMBIGUOUS" for item in contract["requirements"]))

    def test_preference_is_not_authoritative(self):
        contract = build_contract("I'd prefer something elegant.")
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(contract["locked_requirements"], [])
        self.assertEqual(len(contract["requirements"]), 1)
        record = contract["requirements"][0]
        self.assertEqual(record["authority"], "INFERRED_PREFERENCE")
        self.assertFalse(record["eligible_for_lock"])

    def test_conflicting_durations_need_clarification(self):
        contract = build_contract("Make it exactly 10 seconds and around 15 seconds.")
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(contract["locked_requirements"], [])
        self.assertTrue(any(item["clarity"] == "CONFLICTING" for item in contract["requirements"]))

    def test_conflicting_aspect_ratios_need_clarification(self):
        contract = build_contract("Create a vertical 9:16 and vertical 16:9 video.")
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(contract["locked_requirements"], [])
        self.assertTrue(
            all(item["clarity"] == "CONFLICTING" for item in contract["requirements"])
        )

    def test_equivalent_aspect_ratios_are_not_conflicting(self):
        contract = build_contract("Create a vertical 9:16 and vertical 18:32 video.")
        self.assertEqual(contract["status"], "READY")
        self.assertEqual(len(contract["locked_requirements"]), 2)

    def test_conflicting_languages_need_clarification(self):
        contract = build_contract("Create a reel in Marathi and in English.")
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(contract["locked_requirements"], [])
        self.assertTrue(
            all(item["clarity"] == "CONFLICTING" for item in contract["requirements"])
        )

    def test_negated_duration_is_not_locked(self):
        for request in (
            "I don't want a 10-second video.",
            "Do not make it 10 seconds.",
            "Create a video, but I don't want a 10-second video.",
            "Make sure it is not 10 seconds.",
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertNotIn("10-second", contract["locked_requirements"])
                self.assertNotIn("10 seconds", contract["locked_requirements"])

    def test_later_negated_duration_does_not_erase_clear_requirement(self):
        contract = build_contract(
            "Create a 10-second video, but it shouldn't be 15 seconds."
        )
        self.assertEqual(contract["status"], "READY")
        self.assertIn("10-second", contract["locked_requirements"])
        self.assertNotIn("15 seconds", contract["locked_requirements"])

    def test_negated_language_is_not_locked(self):
        for request in (
            "not in Marathi",
            "Create a reel not in Marathi.",
            "I don't want it in Marathi.",
            "Create a video, but not in Marathi.",
            "Create a vertical video, but it isn't in Marathi.",
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertNotIn("in Marathi", contract["locked_requirements"])

    def test_quoted_duration_is_not_locked(self):
        for request in (
            'The phrase "10-second" appears in the example.',
            'Create a reel using the phrase "10-second" as an example.',
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertNotIn("10-second", contract["locked_requirements"])

    def test_duration_discussion_is_not_locked(self):
        for request in (
            "We discussed a 10-second video.",
            "I heard about 10 seconds in a video.",
            "The example: create a 10-second video.",
            "We discussed this example, create a 10-second video.",
            "This is an example; create a 10-second video.",
            "Create a video using the example phrase: 10-second.",
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertNotIn("10-second", contract["locked_requirements"])
                self.assertNotIn("10 seconds", contract["locked_requirements"])

    def test_quoted_language_is_not_locked(self):
        for request in (
            'The quoted language phrase "in Marathi" is discussed.',
            'Create a reel using the phrase "in Marathi" as an example.',
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertNotIn("in Marathi", contract["locked_requirements"])

    def test_language_discussion_is_not_locked(self):
        for request in (
            "We discussed using Marathi.",
            "The example mentions in Marathi.",
            "We discussed this example, in Marathi.",
            "This is an example; in Marathi.",
            "The phrase 'in Marathi' is in this example.",
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertNotIn("in Marathi", contract["locked_requirements"])

    def test_requirement_examples_are_not_locked(self):
        for request in (
            "The example says: create a 10-second video.",
            "Examples include 'Create a 10-second video in Marathi.'",
            "We discussed making a vertical 9:16 video.",
        ):
            with self.subTest(request=request):
                contract = build_contract(request)
                self.assertEqual(contract["locked_requirements"], [])
                self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")

    def test_zero_lock_request_needs_clarification(self):
        contract = build_contract("Make this better.")
        self.assertEqual(contract["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(contract["requirements"], [])

    def test_ready_payload_omits_candidate_output(self):
        contract = build_contract("Create a 10-second reel.")
        payload = canonical_payload(contract)
        self.assertEqual(
            payload,
            {
                "original_request": "Create a 10-second reel.",
                "locked_requirements": ["10-second"],
                "output_type": "text",
            },
        )
        self.assertNotIn("candidate_output", payload)

    def test_clarification_contract_cannot_make_payload(self):
        contract = build_contract("Make this better.")
        with self.assertRaises(ValueError):
            canonical_payload(contract)

    def test_tampered_provenance_cannot_make_payload(self):
        contract = build_contract("Create a 10-second reel.")
        contract["requirements"][0]["source_evidence"] = "15-second"
        with self.assertRaises(ValueError):
            canonical_payload(contract)

    def _assert_tampering_rejected(self, tamper):
        contract = deepcopy(build_contract("Create a 10-second reel."))
        tamper(contract)
        with self.assertRaises(ValueError):
            canonical_payload(contract)

    def test_forged_requirement_text_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract["requirements"][0].update(
                requirement_text="15-second"
            )
        )

    def test_forged_authority_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract["requirements"][0].update(authority="TRUSTED_LOCK")
        )

    def test_forged_clarity_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract["requirements"][0].update(clarity="UNSUPPORTED")
        )

    def test_forged_eligibility_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract["requirements"][0].update(eligible_for_lock=False)
        )

    def test_forged_span_and_evidence_rejected(self):
        def tamper(contract):
            record = contract["requirements"][0]
            record.update(
                requirement_text="Create",
                source_span={"start": 0, "end": 6},
                source_evidence="Create",
                eligible_for_lock=True,
            )
            contract["locked_requirements"] = ["Create"]

        self._assert_tampering_rejected(tamper)

    def test_forged_source_span_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract["requirements"][0].update(
                source_span={"start": 0, "end": 6}
            )
        )

    def test_forged_source_evidence_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract["requirements"][0].update(
                source_evidence="Create"
            )
        )

    def test_forged_locked_requirements_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract.update(locked_requirements=["Create"])
        )

    def test_forced_ready_status_rejected(self):
        contract = build_contract("Make this better.")
        contract["status"] = "READY"
        contract["clarification_issues"] = []
        with self.assertRaises(ValueError):
            canonical_payload(contract)

    def test_changed_request_with_stale_records_rejected(self):
        self._assert_tampering_rejected(
            lambda contract: contract.update(original_request="Use English.")
        )

    def test_arbitrary_source_substring_cannot_be_promoted_to_lock(self):
        def tamper(contract):
            record = contract["requirements"][0]
            record.update(
                requirement_text="reel",
                source_span={"start": 20, "end": 24},
                source_evidence="reel",
                eligible_for_lock=True,
            )
            contract["locked_requirements"] = ["reel"]

        self._assert_tampering_rejected(tamper)

    def test_frozen_core_files_are_unchanged(self):
        core_files = (
            "src/jev_engine/engine.py",
            "src/jev_engine/jev_client.py",
            "src/jev_engine/semantic.py",
            "src/jev_engine/policy.py",
            "src/jev_engine/failure_rules.py",
            "src/jev_engine/v2_shadow.py",
        )
        result = subprocess.run(
            ["git", "diff", "--quiet", FROZEN_BASE, "--", *core_files],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, "Frozen Jev core files differ from V0.1 base")

    def test_adapter_is_unchanged_from_frozen_base(self):
        result = subprocess.run(
            ["git", "diff", "--quiet", FROZEN_BASE, "--", "app/adapter.py"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, "app/adapter.py differs from V0.1 base")


if __name__ == "__main__":
    unittest.main()
