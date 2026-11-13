# Ingestion run leases - Design

Date: 2026-11-13
Status: Draft written on `master` for review; implementation is deferred and tracked in
`docs/backlog.md` (2026-11-13 entry). Not yet planned or implemented.
Source of truth: `2026-10-06-roadmap.md` (the "slices spec"). This design pulls the stuck-run
recovery piece of the roadmap's ingestion-robustness slice (S8) forward. It supersedes the S3
spec's accepted stuck-run costs (`2026-10-12-s3-upload-ingestion-design.md`, decision 2 and the
section 10 risk rows "Worker crash mid-run leaves the run non-terminal" and "a database loss after
the claim still strands that run"), and it changes what decision 2's review fix relies on: the
tasks' transient-database autoretry keeps working before the claim, but after the claim recovery
moves to the sweeper (decision 12). Every other S3 decision stands, and the S3 spec stays frozen.

## 1. Context

On 2026-11-12 an upload (`django_1.pdf`, run `426a0dd8`) stayed in `processing` forever:

1. The worker claimed the run (`queued -> fetching`) and moved it to `processing`.
2. Compose Watch restarted the backend containers; the parse outlived Docker's 10s stop grace
   period and the worker was killed mid-parse.
3. Late acks worked: RabbitMQ re-delivered the unacked message to the restarted worker.
4. The claim (`UPDATE ... WHERE status = 'queued'`) matched zero rows, because the run said
   `processing`. The worker treated the message as a duplicate and acked it.
5. Nothing else ever looks at the run again.

The claim cannot tell "another worker is processing this" from "the worker processing this died":
both look like `processing`. The same gap strands a run when a transient database error hits after
the claim (the task's autoretry re-runs the claim, which no-ops), and when an embed task dies with
its run in `indexing` and its message gone. The S3 spec accepted these costs and deferred the recovery (backlog entry 2026-10-12,
"S7 needs stuck-run recovery").

## 2. Goal and success criteria

Every non-terminal ingestion run either makes progress or ends `failed` within a bounded time,
without manual action, and a slow or frozen worker can never overwrite the work of the worker that
replaced it.

Done when:

- A worker killed mid-ingest or mid-embed has its run re-driven automatically and the run reaches
  `ready` (the 2026-11-12 incident, reproduced as a test at the service interface).
- A run whose message vanished before any claim (consumed and dropped, or lost) is re-published.
- A worker that is alive but hung (a parser loop, a provider call without a timeout) loses its
  lease after `run_max_stage_seconds`, so its run is re-driven like a crashed one.
- A run that keeps getting interrupted ends `failed` with user-safe copy after a bounded number of
  claims per stage, instead of looping forever.
- A stale ("zombie") worker's writes after its run was re-claimed match zero rows.
- Two sweepers running at once re-drive each expired run exactly once.
- The status vocabulary, the uploads API, and the UI are unchanged.
- Runs already stuck when this ships (like `426a0dd8`) are recovered by the first sweep.

## 3. Decisions (2026-11-12/13 design round)

1. **Lease pattern with two columns only.** `ingestion_runs` gains `attempt` and
   `lease_expires_at`; no new status values and no new tables.
2. **Heartbeat renewal** (user choice). A short lease renewed by a background thread while the task
   runs, so a dead worker is detected within about one lease duration. Rejected: a fixed long lease
   (slow recovery, and any task longer than the lease is taken over while alive) and per-stage
   renewal only (one long parse call must still fit in one lease).
3. **The sweeper lives inside the dispatcher loop** (user choice). The dispatcher is already a
   fault-tolerant database polling loop, and a re-drive is just an outbox event that the same loop
   publishes. Rejected: a separate sweeper service (one more container for a few lines of logic)
   and Celery Beat (depends on the broker and worker, the very parts whose failure is recovered
   from, and needs a standalone beat process on Windows).
4. **Two stages, each claimed and counted separately.** The ingest task owns `queued`, `fetching`,
   `processing`; the embed task owns `indexing`. `attempt` resets to 0 when a run enters the embed
   stage, so each stage has its own retry budget. Every guard pairs the attempt with the stage's
   statuses, so ingest attempt 1 and embed attempt 1 cannot be confused.
5. **`attempt` is both the fencing token and the retry counter.** Only a successful claim
   increments it; the sweeper never does. Every outbox payload carries the attempt value the run
   must still hold for the claim to succeed.
6. **The lease also covers waiting.** A run waiting for a worker carries a pickup deadline, so a run
   whose message vanished before any claim is still detected.
7. **All deadlines use the database clock** (`now()`), never a worker's clock, so clock skew between
   containers cannot expire or extend a lease.
8. **Exhaustion ends the run `failed` with stage-specific copy.** The ingest stage's copy points at
   re-upload, which the existing retry path accepts (latest run failed, no document). The embed
   stage already has a document, which the retry path rejects as a duplicate, so its copy points at
   delete and re-upload.
9. **A zombie worker is fenced, not interrupted.** When a heartbeat finds its lease lost, the worker
   logs a warning and stops heartbeating; it does not abort its work. Its later writes match zero
   rows. Aborting in-flight work would add cancellation paths for no correctness gain.
10. **No generic lease framework yet.** Ingestion runs are the only claimed async work today; the
    mechanics live in the ingestion package. A second leased job type is the moment to extract a
    shared module (YAGNI).
11. **A heartbeat proves liveness, so it is capped to also prove progress.** The heartbeat stops
    renewing once its claimed work has run for `run_max_stage_seconds` (its own monotonic clock),
    so a hung worker's lease lapses and the claim budget takes over. This works under every Celery
    pool, including the e2e suite's `--pool=solo`. In addition, both tasks get a Celery hard
    `time_limit` of `run_max_stage_seconds + run_lease_seconds`, which kills a hung prefork child
    and frees its worker slot; it is a no-op under `solo`, which only the e2e suite uses. Rejected:
    the Celery limit alone (unsupported under `solo`, and it gives no recovery guarantee the tests
    can drive without killing processes).
12. **The tasks keep their transient-database autoretry.** Before the claim it still re-runs the
    task within seconds. After the claim a retry carries the old payload attempt and no-ops at the
    claim, so the sweeper recovers the run after about one lease plus one sweep, and that recovery
    spends one claim of the stage's budget. Embed loses its instant post-claim retry. Accepted: a
    run would need three separate database outages during its own processing to fail, and the
    alternative (releasing the claim on a database error) needs the database that just failed.
    Rejected: dropping the autoretry (a pre-claim blip would then wait a full pickup timeout).

## 4. Design

### 4.1 Data model

| Column | Type | Meaning |
| --- | --- | --- |
| `attempt` | `integer not null default 0` | Successful claims of the run's current stage; also the fencing token |
| `lease_expires_at` | `timestamptz null` | The deadline by which the run must progress, or it counts as orphaned |

New constraints and index:

- CHECK `(status IN ('ready', 'failed')) = (lease_expires_at IS NULL)`, built from
  `TERMINAL_RUN_STATUSES` like the existing `finished_at` check: a non-terminal run always has a
  deadline, a terminal run never does.
- CHECK `attempt >= 0`.
- Partial index `ix_ingestion_runs_lease_expires_at` on `lease_expires_at`
  `WHERE lease_expires_at IS NOT NULL`. It holds only the non-terminal runs, so the sweeper's
  scan stays small however much history accumulates.

### 4.2 Lifecycle

`L` = `run_lease_seconds`, `P` = `run_pickup_timeout_seconds`. Each row shows what the writer sets.

| Event | Writer | Status | `attempt` | `lease_expires_at` |
| --- | --- | --- | --- | --- |
| Upload creates the run | api (`request_ingestion`) | `queued` | 0 | `now() + P` |
| Ingest claim | ingest task | `queued -> fetching` | `+1` | `now() + L` |
| Heartbeat | ingest task thread | unchanged | unchanged | `now() + L` |
| Fetch done | ingest task | `fetching -> processing` | unchanged | unchanged |
| Document committed | ingest task (`mark_indexing`) | `processing -> indexing` | reset to 0 | `now() + P` |
| Embed claim | embed task | `indexing` (unchanged) | `+1` | `now() + L` |
| Heartbeat | embed task thread | unchanged | unchanged | `now() + L` |
| Embed done | embed task | `indexing -> ready` | unchanged | `NULL` |
| Identical version | ingest task | `processing -> ready` | unchanged | `NULL` |
| Any failure | either task | `... -> failed` | unchanged | `NULL` |
| Re-drive, ingest running | sweeper | `fetching`/`processing -> queued` | unchanged | `now() + P` |
| Re-drive, waiting | sweeper | `queued` or `indexing` (unchanged) | unchanged | `now() + P` |
| Exhausted | sweeper | `fetching`/`processing`/`indexing -> failed` | unchanged | `NULL` |

`started_at` keeps the first claim's time (`coalesce(started_at, now())`); `finished_at` is set by
every terminal transition exactly as today.

The state machine in `app/ingestion/runs.py` gains two transition pairs, used only by the
sweeper: `(fetching, queued)` and `(processing, queued)`. The embed claim is not a status
transition; it is its own guarded update next to `claim_run`.

### 4.3 Claims and fencing

Both claims are one guarded `UPDATE ... RETURNING attempt`, keyed by run id and the payload's
attempt:

```sql
-- Ingest claim.
UPDATE ingestion_runs
SET status = 'fetching', attempt = attempt + 1, lease_expires_at = now() + :lease,
    started_at = coalesce(started_at, now())
WHERE id = :run_id AND status = 'queued' AND attempt = :payload_attempt
RETURNING attempt;

-- Embed claim.
UPDATE ingestion_runs
SET attempt = attempt + 1, lease_expires_at = now() + :lease
WHERE id = :run_id AND status = 'indexing' AND attempt = :payload_attempt
RETURNING attempt;
```

Zero rows means a duplicate, stale, or superseded delivery: the task acks and does nothing, as
today. On success the task holds the returned value, its **claimed attempt**, and every later write
for that run (each status transition and each heartbeat) adds `AND attempt = :claimed_attempt` to
its existing status guard.

The embed claim runs first, before the document lookup. A claimed run whose document is missing
ends `failed` with `UNEXPECTED_FAILURE` instead of today's silent ack, because a live run without
its document can never finish. (A mid-pipeline delete cascades the run away with the item, so the
claim then matches zero rows and the delivery still no-ops, as today.)

Why this is enough:

- **Duplicate delivery of one message:** the first claim moves `attempt` on; the copy no longer
  matches `:payload_attempt`.
- **Re-delivery after a crash** (the incident): the old message carries the pre-claim attempt, so
  it matches nothing; the sweeper issues a new event with the current attempt once the lease
  expires.
- **Zombie ingest worker:** after the sweeper's re-drive the run is `queued`, so the zombie's
  ingest-stage guards fail at once; after the next claim its attempt is stale as well.
- **Zombie embed worker:** after a re-drive the run stays `indexing` with the same attempt until the
  new claim. Until then the zombie can still finish and mark the run `ready`; that is a complete,
  correct embed, and the new claim then matches nothing (status `ready`). Its heartbeat can also
  push the lease out in that window, which is harmless: the new claim sets its own lease.
  After the new claim, the zombie's writes match zero rows.
- **Partial work by a fenced worker:** the ingest document, its chunks, the embed event, and the
  `indexing` transition commit in one transaction (unchanged), so a fenced `mark_indexing` rolls
  the whole document set back. A fenced embed worker's vector updates are in-place, deterministic
  writes to the same chunks the new claim rewrites.

### 4.4 Heartbeat

A context manager in the ingestion package wraps the claimed work of both tasks:

- It starts a daemon thread that, every `run_heartbeat_seconds`, opens its own short session and
  runs `UPDATE ingestion_runs SET lease_expires_at = now() + :lease WHERE id = :run_id AND
  attempt = :claimed_attempt AND status IN (:stage_statuses)`.
- Zero rows means the lease is lost: the thread logs a warning and exits (decision 9). The warning
  is skipped when the stop event is already set, so the expected race with the task's own final
  commit (a terminal transition or `mark_indexing` lands just before the context exits) stays
  quiet.
- Once the claimed work has run for `run_max_stage_seconds` on the thread's monotonic clock, the
  thread logs a warning and stops renewing (decision 11), so the lease lapses within
  `run_lease_seconds`.
- A database error in one beat is logged and the next beat tries again; if the outage outlasts the
  lease, the sweeper re-drives and fencing keeps the result consistent.
- Exiting the context stops the thread (an `Event`) and joins it, so no beat outlives the task.
- The session factory is injected (production passes the one `session_scope` uses), so the thread
  never shares the task's session, and tests bind it to the test database.

Celery runs tasks in prefork child processes; each child owns its engine and runs at most one task
at a time, so there is one heartbeat thread per running task.

### 4.5 Sweeper

`sweep_expired_runs(db, settings) -> SweepResult` in the ingestion package, called by the
dispatcher loop:

```sql
SELECT id, status, attempt, document_id FROM ingestion_runs
WHERE lease_expires_at < now()
ORDER BY lease_expires_at, id
LIMIT :batch FOR UPDATE SKIP LOCKED;
```

Per selected row, inside the same short transaction:

| Run state | Action |
| --- | --- |
| `fetching`/`processing`/`indexing` with `attempt >= run_max_claims_per_stage` | `-> failed`, stage copy (4.7) |
| `fetching`/`processing`, below the limit | `-> queued`, pickup deadline, new ingest event with the current attempt |
| `queued` | Pickup deadline, new ingest event with the current attempt |
| `indexing` with `document_id IS NULL` | `-> failed`, `UNEXPECTED_FAILURE` (unreachable today; the FK is `SET NULL`, and republishing such a run would loop forever) |
| `indexing`, below the limit | Pickup deadline, new embed event (`document_id` from the run) with the current attempt |

A `queued` run is always below the limit: the sweeper only re-queues runs below it, and only a
claim increments `attempt`. A waiting run is therefore never failed for waiting; while the workers
are down, the sweeper re-publishes it once per pickup timeout, and every extra copy is a cheap
no-op claim.

The re-drive events go through the existing `enqueue_*` helpers, so the transactional outbox still
holds: the run update and its event commit together or not at all, and the dispatcher publishes
them through its normal path.

The dispatcher loop runs one sweep every `run_sweep_interval_seconds` (tracked with an injected
monotonic clock), in its own session and its own try/except, before that tick's dispatch batch, so
re-drive events publish in the same tick and a failing sweep never blocks publishing (or the reverse).

### 4.6 Payload contract

`IngestionRequestedPayload` and `DocumentReadyPayload` in `app/outbox/events.py` gain
`attempt: int`; the enqueue helpers take it as a parameter, and both task signatures gain
`attempt: int = 0`. The default keeps outbox rows and broker messages written before the change
working: their runs hold `attempt = 0` after the migration, which is exactly what those messages
expect. The task-contract test keeps the payload keys and the task parameters in lockstep.

### 4.7 Settings and copy

New settings in `app/core/config.py`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `run_lease_seconds` | 120 | Lease granted by a claim and by each heartbeat |
| `run_heartbeat_seconds` | 30 | Interval between heartbeats |
| `run_pickup_timeout_seconds` | 600 | How long a waiting run may wait before it is re-published |
| `run_max_claims_per_stage` | 3 | Claims per stage before an expired lease fails the run |
| `run_sweep_interval_seconds` | 30 | Interval between sweeps in the dispatcher loop |
| `run_sweep_batch_size` | 50 | Rows locked per sweep |
| `run_max_stage_seconds` | 900 | Longest a claimed stage may run before its heartbeat stops renewing |

Validation: every value is positive; a model validator rejects `run_heartbeat_seconds * 2 >
run_lease_seconds` (at least one missed beat is tolerated before a live worker loses its lease) and
`run_max_stage_seconds < run_lease_seconds`. The 900s default keeps the Celery hard limit
(`900 + 120` seconds) below RabbitMQ's default 30-minute `consumer_timeout`, which would otherwise
close the channel under a long task.

New user-safe copy in `app/ingestion/service.py`, next to the existing table:

- Ingest stage: "Processing was interrupted repeatedly. Upload the file again to retry."
- Embed stage: "Indexing was interrupted repeatedly. Delete the file and upload it again to retry."

### 4.8 Migration

Migration `0008_ingestion_run_leases`:

1. Add `attempt` (`not null`, server default `0`) and `lease_expires_at` (nullable).
2. Backfill `lease_expires_at = now()` for every non-terminal run, so the first sweep picks up the
   runs that are already stuck.
3. Add both CHECK constraints and the partial index.

Downgrade drops the index, the constraints, and the columns. The migration needs a short exclusive
lock on `ingestion_runs`; the table is small.

`lease_expires_at` deliberately has no server default: every writer must set or clear it, and the
CHECK catches a writer that forgets. Old application code violates the CHECK (its inserts carry no
lease and its terminal writes do not clear one), so the app tier (api, worker, dispatcher) must be
stopped before the migration runs. A fresh `docker compose up` already orders it that way, since the
app services wait for `one-off-initialization`; a server deploy stops the app tier first.

### 4.9 Interface changes

- `request_ingestion` takes the pickup timeout, so `upload_file` passes it from settings.
- `ingest_source_item` and `embed_document` (the services) gain `attempt` and an injected
  `session_factory` for the heartbeat. The heartbeat context lives inside the services, because
  the claimed attempt exists only after the claim there; the Celery tasks in `tasks.py` stay thin
  wrappers that pass the payload's `attempt` and `session_scope` through.
- Every guarded transition in `app/ingestion/runs.py` gains a `claimed_attempt` parameter; the
  terminal transitions clear `lease_expires_at`, and `mark_indexing` resets `attempt` and sets the
  pickup deadline.
- The dispatcher's `run_loop` gains the sweep step and an injected monotonic `clock`.

## 5. Failure analysis

The project's async-task questions (`AGENTS.md`), answered per component:

| Component | Runs again after partial progress or success | Two workers at once | Crash recovery |
| --- | --- | --- | --- |
| Ingest task | A stale-attempt message, including a Celery autoretry after the claim, no-ops at the claim; a re-drive re-runs the whole stage, and the document set commits atomically with `indexing`, so nothing half-written survives | One claim wins (status plus attempt guard); the other no-ops | Lease expires, sweeper re-queues, a new claim fences the old worker |
| Embed task | Re-running re-embeds the same chunks in place (deterministic); a post-claim autoretry no-ops at the claim | One claim wins; a pre-claim zombie can only finish the same correct work | Lease expires, sweeper re-publishes, a new claim fences the old worker |
| Hung worker | Not applicable | Fenced like a crashed worker once re-claimed | The heartbeat stops at `run_max_stage_seconds`, the lease lapses, the sweeper re-drives; the Celery hard limit frees the prefork slot |
| Heartbeat | Idempotent: it only moves a deadline forward | Only the holder of the current attempt matches | Dies with its task; the lease then lapses |
| Sweeper | Idempotent: a handled row's new deadline is in the future, so the next sweep skips it | `SKIP LOCKED`: each expired row is handled by exactly one sweeper per expiry | Runs in one transaction; a crash rolls back and the next sweep retries |

External calls that may repeat on a re-drive: the storage GET, the parser call, and the embedding
provider call. They repeat at most `run_max_claims_per_stage` times per stage. With today's stub
providers this costs nothing; once S7's hosted parser and Voyage embeddings land, a re-drive is a
repeated paid call, bounded by the same limit.

The task outcome is durable before the message is acked: late acks stay on, and every claim and
transition commits before the task returns.

Accepted costs and risks:

- **Duplicate messages under a backlog or outage.** A queue backlog or a worker outage longer than
  `run_pickup_timeout_seconds` adds one outbox row and one broker message per waiting run every
  pickup timeout. Each is a no-op claim, but they accumulate for as long as the outage lasts.
- **GIL starvation.** A C-extension parse that holds the GIL longer than
  `run_lease_seconds - run_heartbeat_seconds` (90s at the defaults) starves the heartbeat thread,
  so a live worker is re-driven and fenced. Harmless with the stub parser; S7's real parsers should
  check whether their calls release the GIL, or raise the lease.
- **Post-claim database blips spend claims** (decision 12).

## 6. Testing

Service-interface tests against the test database, using `lease_expires_at` set in the past and
injected intervals instead of real waiting, so none of them should need the `long` marker:

- **Incident regression:** claim an ingest run, stop without finishing, expire the lease,
  re-deliver the original message (no-op), sweep (run `queued`, one new event carrying attempt 1),
  deliver the new event, and see the run reach `ready`.
- **Claims:** a matching claim increments `attempt` and sets the lease; a duplicate delivery and a
  stale-attempt message match zero rows; `mark_indexing` resets `attempt` and sets the pickup
  deadline; every terminal transition clears the lease.
- **Fencing:** worker A claims, the sweeper re-drives, worker B claims; A's transitions and
  heartbeat match zero rows, and A's fenced `mark_indexing` leaves no document behind.
- **Exhaustion:** three expired claims in the ingest stage end `failed` with the ingest copy; the
  same in the embed stage ends `failed` with the embed copy, and the document stays.
- **Waiting:** an expired `queued` run is re-published with an unchanged attempt, any number of
  times, and is never failed.
- **Concurrent sweepers:** two sessions sweep the same expired rows; each run gets exactly one new
  event.
- **Heartbeat:** it renews the lease while the context is open, stops on exit, survives a failing
  beat, reports a lost lease (but not after the stop event is set), and stops renewing once the
  injected clock passes `run_max_stage_seconds`.
- **Embed claim order:** a claimed embed whose document is missing ends `failed`; an embed for a
  deleted item still no-ops.
- **Autoretry after the claim:** a re-run with the original payload no-ops, and the sweeper
  recovers the run.
- **Dispatcher loop:** it sweeps on its interval with an injected clock, a failing sweep does not
  stop the dispatch batch, and a sweep's events publish in the same tick.
- **Schema:** the lease CHECK rejects a terminal run with a lease and a non-terminal run without
  one; the migration backfills non-terminal runs and round-trips on downgrade.
- **Contract:** the payload keys still equal the task parameters, a payload without `attempt` is
  accepted, and both tasks carry the hard `time_limit`.

Existing tests that seed `IngestionRun` rows directly or force a status with a raw `update()`
(`tests/ingestion/test_runs.py`, `tests/ingestion/test_service.py`,
`tests/sources/test_uploads_api.py`) break under the lease CHECK; the plan should budget for
moving them onto one seeding helper that sets a consistent lease.

Manual check after implementation: upload a file in the dev stack, `docker compose kill worker`
while the run is in flight, start the worker again, and watch the row return to `queued` and reach
`ready` within about `run_lease_seconds` plus one sweep interval.

## 7. Documentation to update on implementation

- `docs/2026-10-19-system-overview.md`: the two `ingestion_runs` columns, the dispatcher's sweep
  duty, and the worker's heartbeat.
- `docs/backlog.md`: resolve the 2026-10-12 "S7 needs stuck-run recovery" entry and this spec's
  2026-11-13 entry, with the implementing commits.
- `2026-10-06-roadmap.md`: note in the S8 ingestion-robustness row that stuck-run recovery shipped
  under this design.
- This spec: status to implemented, then frozen.

## 8. Non-goals and follow-ups

- **A longer `stop_grace_period` for the dev worker.** It would make Compose Watch restarts
  interrupt fewer parses, but recovery no longer depends on it. A cheap follow-up, not part of this
  design.
- **Surfacing re-drives in the UI** (for example "retrying, attempt 2"). The row simply returns to
  `queued`; the status vocabulary stays as it is.
- **Aborting a fenced worker's in-flight work** (decision 9).
- **A dead-letter view of exhausted runs.** The error copy on the run is the record for now.
- **A shared lease module** for future async job types (decision 10).
