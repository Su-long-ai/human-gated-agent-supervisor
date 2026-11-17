from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_supervisor.model import AgentLifecycle, RoundState
from agent_supervisor.supervisor import Supervisor


class SupervisorTests(unittest.TestCase):
    def make_sup(self):
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        sup = Supervisor(Path(td.name), stall_after=timedelta(minutes=30))
        sup.bootstrap_main()
        return sup

    def prepare_waiting_commit(self, sup, agent_id="MAIN_AGENT"):
        sup.create_round(agent_id, "test task")
        sup.confirm_project(agent_id)
        sup.confirm_model(agent_id)
        sup.mark_sent(agent_id)
        return sup.current_round(agent_id)

    def test_happy_path_round_completion(self):
        sup = self.make_sup()
        r = self.prepare_waiting_commit(sup)
        sup.write_heartbeat("MAIN_AGENT", r.lease_id, "RUNNING", "working")
        out = sup.commit_round("MAIN_AGENT", r.lease_id, "done", "checkpoint")
        self.assertEqual(out.state, RoundState.ROUND_COMPLETE)

    def test_stale_lease_is_rejected(self):
        sup = self.make_sup()
        self.prepare_waiting_commit(sup)
        with self.assertRaisesRegex(ValueError, "lease"):
            sup.commit_round("MAIN_AGENT", "stale", "x", "y")

    def test_blocked_requires_reason(self):
        sup = self.make_sup()
        r = self.prepare_waiting_commit(sup)
        with self.assertRaisesRegex(ValueError, "reason"):
            sup.write_heartbeat("MAIN_AGENT", r.lease_id, "BLOCKED")

    def test_watchdog_marks_stalled(self):
        sup = self.make_sup()
        r = self.prepare_waiting_commit(sup)
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        sup.write_heartbeat("MAIN_AGENT", r.lease_id, "RUNNING", now=t0)
        out = sup.watchdog("MAIN_AGENT", now=t0 + timedelta(minutes=31))
        self.assertEqual(out.state, RoundState.STALLED)

    def test_child_task_complete_releases_slot(self):
        sup = self.make_sup()
        sup.create_child("RESEARCHER")
        r = self.prepare_waiting_commit(sup, "RESEARCHER")
        out = sup.commit_round(
            "RESEARCHER",
            r.lease_id,
            "finished",
            "safe",
            task_complete=True,
            summary="assignment complete",
        )
        self.assertEqual(out.state, RoundState.TASK_COMPLETE)
        self.assertEqual(sup.agent("RESEARCHER").lifecycle, AgentLifecycle.COMPLETED)

    def test_mailbox_is_addressed_by_logical_agent(self):
        sup = self.make_sup()
        path = sup.send_message("MAIN_AGENT", "RESEARCHER", "inspect module A")
        self.assertTrue(path.exists())

    def test_spawn_request_requires_human_approval(self):
        sup = self.make_sup()
        req = sup.request_child(
            "RESEARCHER",
            role="RESEARCH",
            task="inspect module A",
            reason="parallel review",
        )
        self.assertFalse(sup.store.exists("agents/RESEARCHER/state.json"))
        child = sup.approve_child(req["request_id"])
        self.assertEqual(child.agent_id, "RESEARCHER")
        self.assertTrue(sup.store.exists(f"spawn_requests/approved/{req['request_id']}.json"))
        self.assertFalse(sup.store.exists(f"spawn_requests/pending/{req['request_id']}.json"))

    def test_spawn_denial_does_not_create_child(self):
        sup = self.make_sup()
        req = sup.request_child(
            "RISK_REVIEWER",
            role="REVIEW",
            task="check risk assumptions",
            reason="independent check",
        )
        decision = sup.deny_child(req["request_id"], "not needed for this round")
        self.assertEqual(decision["status"], "DENIED")
        self.assertFalse(sup.store.exists("agents/RISK_REVIEWER/state.json"))
        self.assertTrue(sup.store.exists(f"spawn_requests/denied/{req['request_id']}.json"))

    def test_unsafe_agent_id_is_rejected(self):
        sup = self.make_sup()
        with self.assertRaisesRegex(ValueError, "unsafe"):
            sup.request_child("../escape", "RESEARCH", "x", "y")


if __name__ == "__main__":
    unittest.main()
