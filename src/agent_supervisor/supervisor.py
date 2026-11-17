from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .model import AgentLifecycle, AgentRecord, RoundRecord, RoundState
from .store import JsonStore


class Supervisor:
    def __init__(self, root: Path, stall_after: timedelta = timedelta(minutes=30)):
        self.store = JsonStore(root)
        self.stall_after = stall_after

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat()

    def _agent_path(self, agent_id: str) -> str:
        return f"agents/{agent_id}/state.json"

    def _round_path(self, round_id: str, name: str = "round.json") -> str:
        return f"rounds/{round_id}/{name}"

    def bootstrap_main(self, agent_id: str = "MAIN_AGENT") -> AgentRecord:
        if self.store.exists(self._agent_path(agent_id)):
            return self.agent(agent_id)
        rec = AgentRecord(agent_id=agent_id)
        self.store.write(self._agent_path(agent_id), rec.to_dict())
        return rec

    def agent(self, agent_id: str) -> AgentRecord:
        return AgentRecord.from_dict(self.store.read(self._agent_path(agent_id)))

    def _save_agent(self, rec: AgentRecord) -> None:
        self.store.write(self._agent_path(rec.agent_id), rec.to_dict())

    def create_child(self, agent_id: str) -> AgentRecord:
        if self.store.exists(self._agent_path(agent_id)):
            raise ValueError(f"agent already exists: {agent_id}")
        rec = AgentRecord(agent_id=agent_id)
        self._save_agent(rec)
        return rec

    def create_round(self, agent_id: str, task: str) -> RoundRecord:
        agent = self.agent(agent_id)
        if agent.lifecycle != AgentLifecycle.ACTIVE:
            raise ValueError("only ACTIVE agents can start rounds")
        agent.current_round_number += 1
        self._save_agent(agent)
        round_id = f"{agent_id}-{agent.current_round_number:04d}"
        rec = RoundRecord(
            round_id=round_id,
            agent_id=agent_id,
            generation=agent.generation,
            round_number=agent.current_round_number,
            lease_id=uuid4().hex,
            state=RoundState.WAITING_PROJECT_CONFIRMATION,
            task=task,
        )
        self.store.write(self._round_path(round_id), rec.to_dict())
        self.store.write(f"agents/{agent_id}/current_round.json", {"round_id": round_id})
        return rec

    def current_round(self, agent_id: str) -> RoundRecord:
        ptr = self.store.read(f"agents/{agent_id}/current_round.json")
        return RoundRecord.from_dict(self.store.read(self._round_path(ptr["round_id"])))

    def _save_round(self, rec: RoundRecord) -> None:
        self.store.write(self._round_path(rec.round_id), rec.to_dict())

    def confirm_project(self, agent_id: str) -> RoundRecord:
        rec = self.current_round(agent_id)
        if rec.state != RoundState.WAITING_PROJECT_CONFIRMATION:
            raise ValueError("project confirmation is not expected")
        rec.project_confirmed = True
        rec.state = RoundState.WAITING_MODEL_CONFIRMATION
        self._save_round(rec)
        return rec

    def confirm_model(self, agent_id: str) -> RoundRecord:
        rec = self.current_round(agent_id)
        if rec.state != RoundState.WAITING_MODEL_CONFIRMATION:
            raise ValueError("model confirmation is not expected")
        rec.model_confirmed = True
        rec.state = RoundState.READY_TO_SEND
        self._save_round(rec)
        return rec

    def mark_sent(self, agent_id: str) -> RoundRecord:
        rec = self.current_round(agent_id)
        if rec.state != RoundState.READY_TO_SEND:
            raise ValueError("round is not ready to send")
        rec.state = RoundState.WAITING_COMMIT
        self._save_round(rec)
        return rec

    def _validate_lease(self, rec: RoundRecord, lease_id: str) -> None:
        if rec.lease_id != lease_id:
            raise ValueError("stale or invalid lease")

    def write_heartbeat(
        self,
        agent_id: str,
        lease_id: str,
        status: str,
        progress: str = "",
        reason: str | None = None,
        now: datetime | None = None,
    ) -> None:
        rec = self.current_round(agent_id)
        self._validate_lease(rec, lease_id)
        if rec.state not in {RoundState.WAITING_COMMIT, RoundState.BLOCKED, RoundState.STALLED}:
            raise ValueError("heartbeat is not valid in current state")
        status = status.upper()
        if status not in {"RUNNING", "BLOCKED"}:
            raise ValueError("heartbeat status must be RUNNING or BLOCKED")
        if status == "BLOCKED" and not reason:
            raise ValueError("BLOCKED heartbeat requires a reason")
        ts = now or self._now()
        payload = {
            "round_id": rec.round_id,
            "agent_id": rec.agent_id,
            "generation": rec.generation,
            "lease_id": lease_id,
            "status": status,
            "updated_at": self._iso(ts),
            "progress": progress,
        }
        if reason:
            payload["reason"] = reason
        self.store.write(self._round_path(rec.round_id, "heartbeat.json"), payload)
        rec.state = RoundState.BLOCKED if status == "BLOCKED" else RoundState.WAITING_COMMIT
        self._save_round(rec)

    def watchdog(self, agent_id: str, now: datetime | None = None) -> RoundRecord:
        rec = self.current_round(agent_id)
        if rec.state not in {RoundState.WAITING_COMMIT, RoundState.STALLED}:
            return rec
        hb_path = self._round_path(rec.round_id, "heartbeat.json")
        if not self.store.exists(hb_path):
            return rec
        hb = self.store.read(hb_path)
        updated = datetime.fromisoformat(hb["updated_at"])
        if (now or self._now()) - updated > self.stall_after:
            rec.state = RoundState.STALLED
            self._save_round(rec)
        return rec

    def send_message(self, sender: str, recipient: str, body: str) -> Path:
        msg_id = f"{self._now().strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
        return self.store.write(
            f"mailbox/{recipient}/inbox/{msg_id}.json",
            {
                "message_id": msg_id,
                "sender": sender,
                "recipient": recipient,
                "body": body,
                "created_at": self._iso(self._now()),
            },
        )

    def commit_round(
        self,
        agent_id: str,
        lease_id: str,
        result: str,
        checkpoint: str,
        task_complete: bool = False,
        summary: str = "",
    ) -> RoundRecord:
        rec = self.current_round(agent_id)
        self._validate_lease(rec, lease_id)
        if rec.state not in {
            RoundState.WAITING_COMMIT,
            RoundState.BLOCKED,
            RoundState.STALLED,
        }:
            raise ValueError("commit is not valid in current state")

        self.store.write(
            self._round_path(rec.round_id, "result.json"),
            {"result": result, "checkpoint": checkpoint},
        )
        self.store.write(
            self._round_path(rec.round_id, "commit.json"),
            {
                "round_id": rec.round_id,
                "agent_id": rec.agent_id,
                "generation": rec.generation,
                "lease_id": lease_id,
                "status": "DONE",
                "completed_at": self._iso(self._now()),
            },
        )

        if task_complete:
            self.store.write(
                self._round_path(rec.round_id, "task_completion.json"),
                {
                    "round_id": rec.round_id,
                    "agent_id": rec.agent_id,
                    "generation": rec.generation,
                    "lease_id": lease_id,
                    "status": "TASK_COMPLETE",
                    "summary": summary,
                },
            )
            rec.state = RoundState.TASK_COMPLETE
            agent = self.agent(agent_id)
            if agent_id != "MAIN_AGENT":
                agent.lifecycle = AgentLifecycle.COMPLETED
                self._save_agent(agent)
        else:
            rec.state = RoundState.ROUND_COMPLETE

        self._save_round(rec)
        self.store.write(
            self._round_path(rec.round_id, "commit_receipt.json"),
            {"accepted": True, "lease_id": lease_id, "state": rec.state.value},
        )
        return rec

    def rollover(self, agent_id: str) -> AgentRecord:
        agent = self.agent(agent_id)
        current = self.current_round(agent_id)
        if current.state not in {RoundState.ROUND_COMPLETE, RoundState.TASK_COMPLETE}:
            raise ValueError("rollover requires a safely completed round")
        agent.generation += 1
        self._save_agent(agent)
        return agent
