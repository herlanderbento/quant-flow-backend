"""Operational entry points run as separate processes, exactly as in deployment."""
import os
import subprocess
import sys

from tests.integration.conftest import ROOT, _with_database, ADMIN_URL
from tests.integration.test_worker_recovery import worker_with
from tests.unit.trader.fakes import ScriptedGateway


def run_module(database: str, module: str, *args: str, **env) -> subprocess.CompletedProcess:
    environment = {
        **os.environ,
        "DATABASE_URL": _with_database(ADMIN_URL, database, "postgresql+asyncpg"),
        "PYTHONPATH": str(ROOT / "src"),
        **env,
    }
    return subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT, env=environment,
                          capture_output=True, text=True, timeout=120)


async def test_healthcheck_process_reports_fresh_heartbeat(session_factory, database_name):
    assert run_module(database_name, "trader.infra.worker.healthcheck").returncode == 1  # no worker yet
    await worker_with(session_factory, ScriptedGateway()).run_cycle()
    result = run_module(database_name, "trader.infra.worker.healthcheck")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "healthy" in result.stdout


async def test_seed_and_soak_report_processes(session_factory, database_name, tmp_path):
    refused = run_module(database_name, "trader.infra.ops.seed_paper_bot", "--symbol", "BTC/USDT",
                         TRADING_MODE="testnet")
    assert refused.returncode == 2

    seeded = run_module(database_name, "trader.infra.ops.seed_paper_bot", "--symbol", "BTC/USDT",
                        TRADING_MODE="paper")
    assert seeded.returncode == 0, seeded.stderr
    assert "created bot" in seeded.stdout

    await worker_with(session_factory, ScriptedGateway()).run_cycle()
    evidence = tmp_path / "evidence.json"
    report = run_module(database_name, "trader.infra.ops.soak_report", "--since",
                        "2000-01-01T00:00:00Z", "--out", str(evidence))
    assert report.returncode == 1  # a few seconds are not 24 h
    assert "[FAIL] duration" in report.stdout
    assert evidence.exists()
