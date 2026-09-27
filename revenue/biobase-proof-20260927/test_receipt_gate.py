import unittest
from receipt_gate import classify, summarize


class ReceiptGateTests(unittest.TestCase):
    def test_paid_requires_reconciliation(self):
        d = classify({"task_id": "t1", "state": "paid", "verification": "accepted", "payment": "pending"})
        self.assertEqual((d.disposition, d.reason), ("needs_human", "payment_not_reconciled"))

    def test_paid_and_settled_closes(self):
        d = classify({"task_id": "t2", "state": "paid", "verification": "passed", "payment": "settled"})
        self.assertEqual((d.disposition, d.reason), ("closed", "terminal_paid"))

    def test_delivery_without_verification_escalates(self):
        d = classify({"task_id": "t3", "state": "delivered"})
        self.assertEqual(d.disposition, "needs_human")

    def test_verification_rejection_escalates(self):
        d = classify({"task_id": "t4", "state": "submitted", "verification": "rejected"})
        self.assertEqual((d.disposition, d.reason), ("needs_human", "verification_rejected"))

    def test_expired_closes_without_human_queue(self):
        d = classify({"task_id": "t5", "state": "expired"})
        self.assertEqual(d.disposition, "closed")

    def test_execution_error_escalates(self):
        d = classify({"task_id": "t6", "state": "running", "error": "timeout"})
        self.assertEqual((d.disposition, d.reason), ("needs_human", "execution_error"))

    def test_unknown_state_escalates(self):
        d = classify({"task_id": "t7", "state": "mystery"})
        self.assertEqual(d.disposition, "needs_human")

    def test_missing_task_id_escalates(self):
        d = classify({"state": "running"})
        self.assertEqual((d.task_id, d.disposition), ("<missing>", "needs_human"))

    def test_active_states_stay_active(self):
        for state in ("queued", "running", "claimed", "submitted", "response_received"):
            with self.subTest(state=state):
                d = classify({"task_id": "x", "state": state})
                self.assertEqual(d.disposition, "active")

    def test_summary_only_queues_human_items(self):
        result = summarize([
            {"task_id": "a", "state": "paid", "verification": "accepted", "payment": "settled"},
            {"task_id": "b", "state": "running"},
            {"task_id": "c", "state": "delivered", "verification": "rejected"},
        ])
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["needs_human_count"], 1)
        self.assertEqual(result["human_queue"][0]["task_id"], "c")


if __name__ == "__main__":
    unittest.main()
