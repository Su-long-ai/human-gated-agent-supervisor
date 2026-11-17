# Human-Gated Multi-Agent Supervisor

A small, local-first runtime for coordinating long-running AI agents with **leases, heartbeats, isolated state, mailboxes, human approval gates, and resumable generations**.

This repository is a sanitized public extraction of a larger private supervisor used for real multi-agent research workflows. It contains no private conversation IDs, access tokens, certificates, project data, browser automation, or model-provider credentials.

## Why this exists

Long-running agent work becomes unreliable when stale conversations, duplicate workers, silent timeouts, or ambiguous completion states can mutate the same task.

The supervisor turns that into an explicit state machine:

```text
WAITING_PROJECT_CONFIRMATION
        |
        v
WAITING_MODEL_CONFIRMATION
        |
        v
READY_TO_SEND
        |
        v
WAITING_COMMIT
   |       |       |
heartbeat BLOCKED timeout
   |       |       |
   |       v       v
   |    BLOCKED  STALLED
   |
valid commit
   |
   v
ROUND_COMPLETE ----> next round
   |
task_completion
   |
   v
TASK_COMPLETE
```

## Core ideas

- **Logical agents outlive conversations.** A new generation can replace a conversation without changing the agent identity.
- **Per-round leases.** Heartbeats and commits must match the current lease, so late/stale writes cannot impersonate current work.
- **Human gates.** Child-agent spawn requests stay pending until explicitly approved or denied; the runtime does not auto-send prompts or scrape model UIs.
- **Heartbeats + watchdog.** Stale work is marked `STALLED`; it is not silently retried.
- **Explicit task completion.** Completing one round is different from completing the assigned task.
- **Local mailbox.** Agents communicate through deterministic local files instead of depending on chat URLs.
- **Atomic JSON writes.** State mutations use replace-on-write persistence.
- **Safe logical IDs.** Agent/request identifiers are validated before they can become filesystem paths.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e .
python -m unittest discover -s tests -v
python -m agent_supervisor.demo
```

The public test suite currently covers **9 state/coordination paths**, including stale-lease rejection, watchdog stalls, explicit task completion, spawn approval/denial, mailbox addressing and unsafe-ID rejection.

## Example

```python
from pathlib import Path
from agent_supervisor.supervisor import Supervisor

sup = Supervisor(Path("./demo_state"))
sup.bootstrap_main("MAIN_AGENT")
spawn = sup.request_child(
    "RESEARCHER",
    role="RESEARCH",
    task="Inspect module A",
    reason="parallel review",
)
# Human approval boundary: no child exists before this call.
sup.approve_child(spawn["request_id"])

sup.create_round("MAIN_AGENT", task="Inspect the project and produce a plan")

sup.confirm_project("MAIN_AGENT")
sup.confirm_model("MAIN_AGENT")
sup.mark_sent("MAIN_AGENT")

round_state = sup.current_round("MAIN_AGENT")
sup.write_heartbeat(
    "MAIN_AGENT",
    lease_id=round_state.lease_id,
    status="RUNNING",
    progress="reviewing files",
)

sup.commit_round(
    "MAIN_AGENT",
    lease_id=round_state.lease_id,
    result="review complete",
    checkpoint="safe stopping point",
)
```

## Repository layout

```text
src/agent_supervisor/
  model.py        state and lifecycle models
  store.py        atomic local persistence
  supervisor.py   transitions, leases, heartbeat/commit validation
  demo.py         runnable example
tests/
  test_supervisor.py
```

## What is intentionally not included

The private system also has richer GUIs, mobile control, project-specific integrations and operational history. Those are not needed to demonstrate the core design and would leak machine-specific or private state.

This public extraction contains **no browser automation and no automatic model UI control**.

## Portfolio signal

This project demonstrates:

- multi-agent orchestration;
- state-machine design;
- failure containment;
- lease/heartbeat coordination;
- resumable workflows;
- human-in-the-loop control;
- testable local infrastructure.

## License

MIT
