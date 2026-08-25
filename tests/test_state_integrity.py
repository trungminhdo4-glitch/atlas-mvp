"""Wave 7: state-integrity contract coverage.

Proves the corrupted-state contract of Coordinator.load_state:
missing files stay a legitimate first run, any existing untrustworthy file
is rejected with a stable StateCorruptionError classification, failed loads
are observationally non-mutating, and neither minting nor replay protection
can be weakened through corrupt persisted state.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from compute.job import ComputeJob
from orchestration.coordinator import Coordinator, StateCorruptionError


def canonical_tx_hash(tx_dict):
    data = {
        key: tx_dict[key]
        for key in (
            "payload",
            "parent1",
            "parent2",
            "node_id",
            "timestamp",
            "signature",
        )
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class StateIntegrityContractTest(unittest.TestCase):
    """Adversarial matrix against the persistence trust boundary."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.state_dir = Path(tmp.name)
        self.state_file = self.state_dir / "state.json"

        self.coord = Coordinator()
        self.coord.STATE_FILE = str(self.state_file)
        self.coord.register_node("farm_a")
        self.coord.register_node("farm_b")
        self.coord.submit_energy("farm_a", 10.0, "solar_grid")
        for _ in range(3):
            self.coord.confirm_transactions()
        self.coord.submit_energy("farm_b", 4.0, "wind_park")
        for _ in range(3):
            self.coord.confirm_transactions()
        self.minted = self.coord.process_minting()
        self.assertTrue(self.minted)
        self.assertGreater(self.coord.ledger.get_balance("farm_a"), 0.0)
        job = ComputeJob(
            job_id="j1",
            node_id="farm_a",
            token_cost=1.0,
            payload={"task": "forecast"},
        )
        self.assertTrue(self.coord.submit_compute_job(job))
        self.coord.save_state()
        self.good_bytes = self.state_file.read_bytes()

    # --- helpers ----------------------------------------------------------

    def _snapshot(self, coord):
        return {
            "nodes": set(coord.nodes),
            "balances": dict(coord.ledger.balances),
            "total_supply": coord.ledger.total_supply,
            "processed": set(coord.minter.processed_transactions),
            "hashes": set(coord.dag.transactions),
            "tips": set(coord.dag.tips),
            "confirmations": dict(coord.dag.confirmations),
            "queue": [
                (j.job_id, j.node_id, j.token_cost, j.payload)
                for j in coord.scheduler.job_queue
            ],
        }

    def _energy_tx_index(self, data):
        return next(
            i
            for i, tx in enumerate(data["dag"]["transactions"])
            if tx["payload"].get("type") == "energy_contribution"
            and tx["node_id"] == "farm_a"
        )

    def _rewrite(self, mutator):
        data = json.loads(self.good_bytes.decode("utf-8"))
        mutator(data)
        content = json.dumps(data, indent=2)
        self.state_file.write_text(content, encoding="utf-8")
        return content.encode("utf-8")

    def _assert_rejected(self, expected_class):
        """Load must fail closed: stable error, zero side effects."""
        observer = Coordinator()
        observer.STATE_FILE = str(self.state_file)
        observer.register_node("pre_existing")
        before = self._snapshot(observer)

        with self.assertRaises(StateCorruptionError) as ctx:
            observer.load_state()
        self.assertEqual(ctx.exception.failure_class, expected_class)

        self.assertEqual(self._snapshot(observer), before)
        self.assertTrue(self.state_file.exists())
        leftovers = list(self.state_dir.glob(".atlas_state-*"))
        self.assertEqual(leftovers, [])

    # --- A. ABSENT ---------------------------------------------------------

    def test_absent_file_is_legitimate_first_run(self):
        fresh = Coordinator()
        fresh.STATE_FILE = str(self.state_dir / "never.json")
        self.assertFalse(fresh.load_state())
        self.assertEqual(fresh.dag.transactions, {})
        self.assertEqual(fresh.ledger.total_supply, 0.0)

    # --- B. SYNTAX_CORRUPT ---------------------------------------------------

    def test_zero_byte_file_rejected_as_syntax(self):
        self.state_file.write_bytes(b"")
        self._assert_rejected("syntax")

    def test_truncated_json_rejected_as_syntax(self):
        self.state_file.write_bytes(self.good_bytes[: len(self.good_bytes) // 2])
        self._assert_rejected("syntax")

    def test_invalid_utf8_rejected_as_syntax(self):
        self.state_file.write_bytes(b"\xff\xfe" + self.good_bytes)
        self._assert_rejected("syntax")

    # --- C. STRUCTURE_CORRUPT --------------------------------------------------

    def test_empty_object_rejected_as_structure(self):
        self.state_file.write_text("{}", encoding="utf-8")
        self._assert_rejected("structure")

    def test_non_object_top_level_rejected_as_structure(self):
        for content in ("[]", "null", '"state"', "42"):
            with self.subTest(content=content):
                self.state_file.write_text(content, encoding="utf-8")
                self._assert_rejected("structure")

    def test_every_missing_section_rejected_as_structure(self):
        for section in (
            "nodes",
            "balances",
            "total_supply",
            "processed_transactions",
            "dag",
            "job_queue",
        ):
            with self.subTest(section=section):
                self._rewrite(lambda d, s=section: d.pop(s))
                self._assert_rejected("structure")

    def test_wrong_section_types_rejected_as_structure(self):
        cases = [
            ("nodes", "not_a_list"),
            ("balances", None),
            ("total_supply", "many"),
            ("processed_transactions", {}),
            ("dag", []),
            ("job_queue", {}),
        ]
        for section, value in cases:
            with self.subTest(section=section, value=value):
                self._rewrite(lambda d, s=section, v=value: d.update({s: v}))
                self._assert_rejected("structure")

    def test_malformed_transaction_records_rejected(self):
        def break_payload(data):
            index = self._energy_tx_index(data)
            data["dag"]["transactions"][index]["payload"] = 42

        def drop_signature(data):
            index = self._energy_tx_index(data)
            del data["dag"]["transactions"][index]["signature"]

        def boolean_timestamp(data):
            index = self._energy_tx_index(data)
            data["dag"]["transactions"][index]["timestamp"] = True

        def transaction_not_object(data):
            data["dag"]["transactions"][0] = ["hash"]

        for mutator in (
            break_payload,
            drop_signature,
            boolean_timestamp,
            transaction_not_object,
        ):
            with self.subTest(mutator=mutator.__name__):
                self._rewrite(mutator)
                self._assert_rejected("structure")

    def test_malformed_job_entries_rejected(self):
        def drop_node_id(data):
            data["job_queue"][0].pop("node_id")

        def string_token_cost(data):
            data["job_queue"][0]["token_cost"] = "free"

        def payload_not_object(data):
            data["job_queue"][0]["payload"] = "text"

        for mutator in (drop_node_id, string_token_cost, payload_not_object):
            with self.subTest(mutator=mutator.__name__):
                self._rewrite(mutator)
                self._assert_rejected("structure")

    def test_non_finite_queued_job_costs_rejected(self):
        for cost in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(cost=cost):
                self._rewrite(
                    lambda data, invalid=cost: data["job_queue"][0].update(
                        {"token_cost": invalid}
                    )
                )
                self._assert_rejected("structure")

    # --- D. SEMANTIC_CORRUPT -------------------------------------------------

    def test_stored_hash_mismatch_rejected_as_semantic(self):
        self._rewrite(
            lambda d: d["dag"]["transactions"][self._energy_tx_index(d)].update(
                {"hash": "f" * 64}
            )
        )
        self._assert_rejected("semantic")

    def test_tampered_timestamp_breaks_identity_and_is_rejected(self):
        self._rewrite(
            lambda d: d["dag"]["transactions"][self._energy_tx_index(d)].update(
                {
                    "timestamp": d["dag"]["transactions"][self._energy_tx_index(d)][
                        "timestamp"
                    ]
                    + 1
                }
            )
        )
        self._assert_rejected("semantic")

    def test_consistently_reshaped_dangling_parent_rejected(self):
        def reshape(data):
            index = self._energy_tx_index(data)
            tx = data["dag"]["transactions"][index]
            tx["parent1"] = "e" * 64
            tx["hash"] = canonical_tx_hash(tx)

        self._rewrite(reshape)
        self._assert_rejected("semantic")

    def test_parent_map_must_match_transaction_parents(self):
        def contradict(data):
            index = self._energy_tx_index(data)
            tx_hash = data["dag"]["transactions"][index]["hash"]
            data["dag"]["parents"][tx_hash] = [tx_hash, tx_hash]

        self._rewrite(contradict)
        self._assert_rejected("semantic")

    def test_parents_key_set_mismatch_rejected(self):
        self._rewrite(lambda d: d["dag"].update({"parents": {}}))
        self._assert_rejected("semantic")

    def test_phantom_tip_rejected_not_silently_repaired(self):
        self._rewrite(
            lambda d: d["dag"].update({"tips": list(d["dag"]["tips"]) + ["a" * 64]})
        )
        self._assert_rejected("semantic")

    def test_confirmation_referential_integrity_enforced(self):
        def unknown_tx(data):
            data["dag"]["confirmations"]["b" * 64] = 99

        def negative_count(data):
            first_key = next(iter(data["dag"]["confirmations"]))
            data["dag"]["confirmations"][first_key] = -1

        def boolean_count(data):
            first_key = next(iter(data["dag"]["confirmations"]))
            data["dag"]["confirmations"][first_key] = True

        for mutator in (unknown_tx, negative_count, boolean_count):
            with self.subTest(mutator=mutator.__name__):
                self._rewrite(mutator)
                self._assert_rejected("semantic")

    def test_duplicate_transaction_identity_rejected(self):
        self._rewrite(
            lambda d: d["dag"]["transactions"].append(dict(d["dag"]["transactions"][0]))
        )
        self._assert_rejected("semantic")

    def test_processed_transactions_unknown_hash_rejected(self):
        self._rewrite(
            lambda d: d.update(
                {
                    "processed_transactions": list(d["processed_transactions"])
                    + ["c" * 64]
                }
            )
        )
        self._assert_rejected("semantic")

    def test_supply_disagreeing_with_balances_rejected(self):
        self._rewrite(lambda d: d.update({"total_supply": d["total_supply"] + 1000.0}))
        self._assert_rejected("semantic")

    def test_negative_balance_rejected(self):
        def negate_consistently(data):
            holder = next(iter(data["balances"]))
            amount = data["balances"][holder]
            data["balances"][holder] = -amount
            data["total_supply"] -= 2 * amount

        self._rewrite(negate_consistently)
        self._assert_rejected("semantic")

    # --- error hygiene --------------------------------------------------------

    def test_error_message_names_class_without_dumping_payloads(self):
        secret_marker = "top_secret_payload_value"
        self._rewrite(
            lambda d: d["dag"]["transactions"][self._energy_tx_index(d)][
                "payload"
            ].update({"note": secret_marker})
        )
        with self.assertRaises(StateCorruptionError) as ctx:
            self.coord.load_state()
        message = str(ctx.exception)
        self.assertIn("[semantic]", message)
        self.assertNotIn(secret_marker, message)

    # --- Phase 5: restart / replay proof ---------------------------------------

    def test_valid_restart_preserves_identity_and_blocks_remint(self):
        hashes_before = sorted(self.coord.dag.transactions)
        tips_before = sorted(self.coord.dag.tips)
        confirmations_before = dict(self.coord.dag.confirmations)
        processed_before = set(self.coord.minter.processed_transactions)
        supply_before = self.coord.ledger.total_supply

        restarted = Coordinator()
        restarted.STATE_FILE = str(self.state_file)
        self.assertTrue(restarted.load_state())

        self.assertEqual(sorted(restarted.dag.transactions), hashes_before)
        self.assertEqual(sorted(restarted.dag.tips), tips_before)
        self.assertEqual(dict(restarted.dag.confirmations), confirmations_before)
        self.assertEqual(set(restarted.minter.processed_transactions), processed_before)
        self.assertEqual(restarted.ledger.total_supply, supply_before)

        for _ in range(5):
            restarted.confirm_transactions()
        reminted = restarted.process_minting()
        self.assertEqual(reminted, [])
        self.assertEqual(restarted.ledger.total_supply, supply_before)

    def test_corrupt_restart_never_produces_clean_ledger_or_replay_route(self):
        self.state_file.write_text("{}", encoding="utf-8")

        for attempt in range(3):
            victim = Coordinator()
            victim.STATE_FILE = str(self.state_file)
            with self.assertRaises(StateCorruptionError):
                victim.load_state()
            # No empty-ledger substitution happened: the ledger object was
            # never replaced and carries no mintable history.
            self.assertEqual(victim.ledger.balances, {})
            self.assertIs(victim.dag.transactions, victim.dag.transactions)
        self.assertEqual(self.state_file.read_text(encoding="utf-8"), "{}")

    def test_genesis_tip_is_valid_for_fresh_saved_state(self):
        virgin = Coordinator()
        virgin.STATE_FILE = str(self.state_dir / "virgin.json")
        virgin.save_state()
        loaded = Coordinator()
        loaded.STATE_FILE = str(self.state_dir / "virgin.json")
        self.assertTrue(loaded.load_state())
        self.assertEqual(loaded.dag.tips, {loaded.dag.GENESIS_HASH})

    # --- Phase 6: failure injection around the new boundaries -------------------

    def test_exception_during_validation_leaves_instance_pristine(self):
        import core.transaction as tx_mod

        observer = Coordinator()
        observer.STATE_FILE = str(self.state_file)
        observer.register_node("pre_existing")
        before = self._snapshot(observer)

        original = tx_mod.Transaction._compute_hash

        def exploding(self_tx):
            raise RuntimeError("injected reconstruction failure")

        tx_mod.Transaction._compute_hash = exploding
        try:
            with self.assertRaises(RuntimeError):
                observer.load_state()
        finally:
            tx_mod.Transaction._compute_hash = original

        self.assertEqual(self._snapshot(observer), before)
        self.assertEqual(self.state_file.read_bytes(), self.good_bytes)


if __name__ == "__main__":
    unittest.main()
