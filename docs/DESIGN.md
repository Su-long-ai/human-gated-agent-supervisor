# Design Notes

## System goal

The supervisor coordinates long-running **logical agents** without pretending that a chat conversation is a durable worker process.

The public extraction focuses on four problems:

1. stale work must not be accepted as current work;
2. a silent worker must be observable without being duplicated automatically;
3. spawning parallel workers must cross an explicit human boundary;
4. conversation rollover must not destroy logical agent identity.

## Core invariants

### One round, one lease

Every round has a random lease ID. A heartbeat or commit is accepted only when its lease matches the current round.

This protects against:

- a previous conversation writing late;
- a retried/duplicated worker committing after ownership changed;
- a stale generation accidentally completing a newer round.

A lease is intentionally simpler than a distributed lock: the runtime is local-first and does not need consensus. It only needs **ownership freshness**.

### Logical agent != conversation

The durable identity is the local `agent_id`. A conversation is only a generation-specific reasoning container.

That lets the runtime roll over context while keeping:

- the same mailbox address;
- the same long-term state location;
- the same task identity;
- an explicit generation number for stale-write rejection.

### STALLED is observable, not self-healing

The watchdog marks stale work as `STALLED`, but it does **not** launch a duplicate automatically.

Why:

- the original worker may still be alive but temporarily unable to heartbeat;
- automatic duplication can create conflicting side effects;
- retry policy is task-specific and should not be hidden in infrastructure.

The supervisor therefore separates **detection** from **recovery authority**.

### Spawn requests are proposals

`request_child()` creates a pending request, not a worker. `approve_child()` is the explicit authority boundary.

That makes resource expansion auditable and prevents an agent from silently multiplying its own execution capacity.

### Resource growth is bounded

Human approval is necessary but not sufficient for child creation. The runtime also enforces configurable active-child and total-agent limits. A completed child changes lifecycle and releases capacity instead of permanently consuming a slot.

This keeps the control boundary explicit even when MAIN requests many parallel workers.

### Round completion != task completion

A round is a bounded unit of work. An assigned task can span many rounds.

The runtime keeps `ROUND_COMPLETE` and `TASK_COMPLETE` separate so a safe checkpoint cannot accidentally reclaim a still-needed worker.

## Persistence model

State is stored as small JSON records written through atomic replace-on-write persistence.

The public implementation intentionally avoids a database because:

- the state volume is tiny;
- files are easy to inspect during failures;
- each record has a clear owner and lifecycle;
- the goal is to demonstrate coordination semantics, not database scale.

A larger deployment could move the same state machine to SQLite/PostgreSQL without changing the ownership model.

## Failure modes

| Failure | Expected behavior |
| --- | --- |
| old conversation writes a commit | rejected by lease mismatch |
| heartbeat stops | round becomes `STALLED` |
| worker explicitly blocks | round becomes `BLOCKED` with reason |
| child spawn requested | remains pending until approve/deny |
| unsafe logical ID | rejected before becoming a filesystem path |
| child finishes assignment | lifecycle becomes `COMPLETED` |
| conversation context grows too large | rollover increments generation after safe completion |

## Deliberate non-goals

The public runtime does not:

- scrape model UI/DOM state;
- auto-send prompts;
- automatically retry stalled work;
- provide distributed consensus;
- claim exactly-once execution across arbitrary external side effects.

Those would be separate layers with different threat and consistency models.

## What I would add next

For a production multi-user deployment:

- authenticated API boundaries;
- database-backed event log;
- per-project quotas and RBAC;
- idempotency keys for external side effects;
- structured metrics/tracing;
- explicit retry policies per task class;
- load and recovery tests.
