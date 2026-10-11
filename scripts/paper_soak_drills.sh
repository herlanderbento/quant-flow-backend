#!/usr/bin/env bash
# Unattended drills + evidence for the paper soak (docs/PAPER_SOAK_TEST.md).
# Acts ONLY on the quantflow_paper project; never touches the dev stack.
#
#   scripts/paper_soak_drills.sh <since-UTC> <start-UTC> [report-hours]
#     since-UTC : value for soak_report --since (before the first worker started)
#     start-UTC : drill clock origin (bots seeded); drills at +6h, +12h, +18h
#
# Evidence goes to artifacts/reports/soak/run_<start>/ (git-ignored). No secrets are
# printed: worker logs are JSON with sensitive fields redacted, and any line carrying a
# connection string is dropped defensively.
set -u
cd "$(dirname "$0")/.."

SINCE="$1"
START="$2"
REPORT_HOURS="${3:-24}"
COMPOSE=(docker compose --env-file .env.paper -f docker-compose.paper.yml)
WORKER=quantflow_paper-paper_worker-1
DB=quantflow_paper-paper_db-1
RUN_DIR="artifacts/reports/soak/run_${START//:/}"
LOG="$RUN_DIR/drills.log"
mkdir -p "$RUN_DIR"

utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(utc) $*" | tee -a "$LOG"; }
epoch() { date -u -d "$1" +%s; }
scrub() { grep -v -E '://[^ ]*@' ; }

START_S=$(epoch "$START")

status_snapshot() {
  docker exec "$DB" psql -U quantflow_paper -d quantflow_paper -tA -F ' | ' -c \
    "select worker_id, started_at, last_heartbeat_at, stopped_at, cycles_total, cycle_errors_total,
            consecutive_failures, max_cycle_gap_seconds, last_market_data_at, last_audit_at, audit_issues
       from worker_status order by started_at" >> "$RUN_DIR/status.log" 2>&1
  echo "--- $(utc)" >> "$RUN_DIR/status.log"
}

wait_healthy() {  # $1 = label; logs seconds until the worker healthcheck passes
  local t0=$(date +%s)
  while (( $(date +%s) - t0 < 900 )); do
    if docker exec "$WORKER" python -m trader.infra.worker.healthcheck >/dev/null 2>&1; then
      log "$1: worker healthy after $(( $(date +%s) - t0 ))s"
      return 0
    fi
    sleep 5
  done
  log "$1: worker NOT healthy after 900s"
  return 1
}

sleep_until() {  # hours after START, with hourly status snapshots meanwhile
  local target=$(( START_S + $1 * 3600 ))
  while (( $(date +%s) < target )); do
    status_snapshot
    local left=$(( target - $(date +%s) ))
    sleep $(( left < 3600 ? (left > 0 ? left : 0) : 3600 ))
  done
}

log "drills started; since=$SINCE start=$START report_hours=$REPORT_HOURS pid=$$"
status_snapshot

sleep_until 6
log "DRILL 1 (worker crash): docker kill $WORKER"
docker kill "$WORKER" >> "$LOG" 2>&1
sleep 2
wait_healthy "DRILL 1" || { log "DRILL 1: AUTOMATIC RECOVERY FAILED (recorded as a failure); starting the worker manually"; docker start "$WORKER" >> "$LOG" 2>&1; wait_healthy "DRILL 1 manual"; }
status_snapshot

sleep_until 12
log "DRILL 2 (database restart): docker restart $DB"
docker restart "$DB" >> "$LOG" 2>&1
wait_healthy "DRILL 2" || { log "DRILL 2: AUTOMATIC RECOVERY FAILED (recorded as a failure); starting the worker manually"; docker start "$WORKER" >> "$LOG" 2>&1; wait_healthy "DRILL 2 manual"; }
status_snapshot

sleep_until 18
log "DRILL 3 (graceful stop): compose stop paper_worker"
"${COMPOSE[@]}" stop paper_worker >> "$LOG" 2>&1
log "DRILL 3: stopped; starting again"
"${COMPOSE[@]}" start paper_worker >> "$LOG" 2>&1
wait_healthy "DRILL 3" || { log "DRILL 3: AUTOMATIC RECOVERY FAILED (recorded as a failure); starting the worker manually"; docker start "$WORKER" >> "$LOG" 2>&1; wait_healthy "DRILL 3 manual"; }
docker logs --since "$(( $(date +%s) - 600 ))" "$WORKER" 2>&1 | scrub \
  | grep -E "Received SIGTERM|BotWorker stopped|BotWorker started" >> "$LOG"
status_snapshot

sleep_until "$REPORT_HOURS"
sleep 600  # margin so the measured duration clears the threshold
log "REPORT: soak_report --since $SINCE --min-hours 24"
"${COMPOSE[@]}" exec -T paper_worker python -m trader.infra.ops.soak_report \
  --since "$SINCE" --min-hours 24 --out /tmp/soak.json 2>&1 | scrub | tee "$RUN_DIR/soak_report.txt"
log "REPORT exit code: ${PIPESTATUS[0]}"
"${COMPOSE[@]}" cp paper_worker:/tmp/soak.json "$RUN_DIR/soak_report.json" >> "$LOG" 2>&1

# Manual-checklist evidence. Logs of earlier containers are gone after `docker kill`
# (same container, so they are kept); this captures what the engine still has.
docker logs "$WORKER" 2>&1 | scrub > "$RUN_DIR/worker.log"
{
  echo "BotWorker started lines:"; grep -c "BotWorker started" "$RUN_DIR/worker.log"
  echo "...of which TRADING_MODE=paper:"; grep -c "BotWorker started in TRADING_MODE=paper" "$RUN_DIR/worker.log"
  echo "Traceback lines:"; grep -c "Traceback" "$RUN_DIR/worker.log"
  echo "ERROR lines:"; grep -c '"level": "ERROR"' "$RUN_DIR/worker.log"
  echo "ALERT lines:"; grep -c "ALERT" "$RUN_DIR/worker.log"
  echo "Bot outcomes:"; grep -o '"outcome": "[A-Z_]*"' "$RUN_DIR/worker.log" | sort | uniq -c
} > "$RUN_DIR/log_summary.txt"
status_snapshot
log "drills finished; stack left running"
