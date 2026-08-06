# Scheduled Task Catch-up Plan Archive

Archived on: 2026-06-11

## Background

The system has scheduled tasks such as the auto order pipeline running at fixed daily times. The current question is how to make these tasks automatically recover when a planned execution is missed, for example because the backend process was stopped, redeployed, or unavailable at the scheduled time.

This document records the proposed solution and open questions only. It does not represent an implementation.

## Current Findings

- Scheduled tasks are registered in `caifuclaw_business_app/app/scheduler.py` with APScheduler.
- Cron-style tasks are scheduled directly from `scheduled_tasks.cron_expr`.
- Interval-style tasks are scheduled again after each run finishes.
- Task runs are persisted in `scheduled_task_runs`.
- Existing failure retry already exists through `waiting_retry`, `next_retry_at`, and `process_due_task_retries()`.
- Scheduler leader protection already exists through PostgreSQL advisory lock and heartbeat logic.
- `scheduled_task_runs` currently does not store an expected/planned execution time such as `scheduled_for`.
- Because there is no planned execution timestamp, the system cannot reliably know whether a specific cron occurrence, such as `2026-06-11 08:10`, was missed or already handled.

## Recommended Scope

Start with cron scheduled tasks only.

Recommended default behavior:

- Look back 24 hours for missed cron occurrences.
- Compensate each missed occurrence at most once.
- Do not run the same scheduled task concurrently.
- Record catch-up runs explicitly in task logs.
- Let catch-up runs reuse the existing task execution flow and failure retry mechanism.
- Keep the existing normal cron execution behavior unchanged.

Interval-style tasks should not be catch-up replayed initially. When the service recovers, the interval task can simply schedule and run again from the current time.

## Proposed Design

### 1. Persist Planned Execution Time

Add a planned execution timestamp to task run records.

Suggested field:

- `scheduled_for TIMESTAMP NULL`

Meaning:

- Normal cron run: the cron occurrence time.
- Catch-up run: the missed cron occurrence time.
- Manual run: `NULL`.
- Retry run: inherit the original run's `scheduled_for`.

This makes a run traceable by both actual start time and intended schedule time.

### 2. Add Deduplication

Add a database-level uniqueness rule so the same task occurrence cannot be executed twice.

Suggested logical key:

- `scheduled_task_id + scheduled_for`

Only applies when `scheduled_for IS NOT NULL`.

This prevents duplicate execution if the scheduler and catch-up scanner race, or if multiple processes scan at the same time.

### 3. Add Catch-up Scanner

Add a scanner that periodically checks enabled cron tasks.

For each enabled cron task:

1. Calculate expected cron fire times between `now - lookback_window` and `now`.
2. Exclude future occurrences.
3. Check whether a run already exists for `scheduled_task_id + scheduled_for`.
4. Check whether the same task is currently running.
5. If safe, create and execute a catch-up run.

Suggested trigger mode:

- `catchup`

### 4. Run Catch-up on Startup

After the scheduler leader starts and reloads jobs, immediately run one catch-up scan.

This covers:

- service restart,
- deployment,
- host reboot,
- process crash recovery.

### 5. Run Catch-up Periodically

Add a periodic scanner job.

Suggested config:

- `scheduled_task_catchup_scan_interval_seconds = 60`
- `scheduled_task_catchup_lookback_hours = 24`
- `scheduled_task_catchup_max_runs_per_scan = 5`

The max-runs limit avoids a long outage causing a large burst of printing/purchasing work all at once.

### 6. Reuse Existing Retry Flow

If a catch-up run fails, it should use the existing retry mechanism:

- `waiting_retry`
- `next_retry_at`
- `retry`
- final failure email

No separate retry system is needed.

### 7. Add Log Visibility

Task logs should expose:

- trigger mode: `scheduler`, `manual`, `retry`, `catchup`
- planned execution time: `scheduled_for`
- actual start time: `started_at`
- actual end time: `ended_at`
- retry chain fields already present

This allows operators to see whether a run was on time or automatically compensated.

## Impact on Existing Tasks

If implemented conservatively, normal scheduled task behavior should not change.

Expected changes:

- Existing cron jobs still run at their configured times.
- Missed cron occurrences can create additional `catchup` runs after recovery.
- Logs will include extra catch-up runs.
- Database schema will gain at least one field and one uniqueness rule/index.
- Failed catch-up runs will enter the existing retry flow.

Main risks:

- Duplicate execution if `scheduled_for` uniqueness and task-level mutual exclusion are not implemented.
- Unexpected work burst after long downtime if the lookback window or max-runs limit is too large.
- Duplicate printing or purchase generation if business idempotency is incomplete.

Current business safeguards observed:

- The auto order pipeline selects only pending/waiting-print/waiting-purchase orders that still need processing.
- Purchase generation uses existing-source checks through `allow_existing=True`.
- Printed labels are marked on orders through `label_printed_at`.

These safeguards help, but they should not replace a run-level deduplication key.

## Open Questions

1. What lookback window should be used for missed cron tasks?
   - Recommended: 24 hours.

2. If the service is down for several days, should the system run every missed occurrence or only the latest one?
   - Recommended: cap by `scheduled_task_catchup_max_runs_per_scan` and review after observing production behavior.

3. Should disabled tasks be ignored even if they were enabled at the missed time?
   - Recommended: ignore currently disabled tasks.

4. If a task is currently running, should the missed occurrence wait, skip, or try again in the next scan?
   - Recommended: wait and try again in the next scan.

5. Should manual runs count as satisfying a missed scheduled occurrence?
   - Recommended: no, unless the manual run is explicitly linked to a `scheduled_for` value.

6. Should interval tasks receive catch-up behavior?
   - Recommended: no for the first implementation.

7. Should the admin UI include a manual "run catch-up scan" button?
   - Recommended: optional, useful after deployment but not required for the first version.

8. Should catch-up scan activity have its own audit log?
   - Recommended: yes if operators need to explain why a task ran outside its normal time.

## Suggested Acceptance Criteria

- When the backend is stopped during a cron fire time and later restarted, the missed occurrence is automatically detected and executed once.
- A catch-up run is visible in task logs with trigger mode `catchup`.
- The run shows both planned execution time and actual start time.
- The same task occurrence cannot be executed twice.
- If a catch-up run fails, it enters the existing retry mechanism.
- If a task is disabled, no catch-up run is created.
- If the same task is already running, the scanner does not start another concurrent run.

