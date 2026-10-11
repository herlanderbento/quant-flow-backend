"""The long-running process must be PID 1 (`exec`), or SIGTERM never reaches it.

With `sh -c "a && b"` the shell stays PID 1, ignores SIGTERM, and `docker stop` ends in
SIGKILL after the grace period: no graceful worker shutdown, no stopped_at heartbeat.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = ["docker-compose.yml", "docker-compose.paper.yml", "docker-compose.testnet.yml", "Dockerfile"]
LONG_RUNNING = re.compile(r"(python -m trader\.infra\.worker|uvicorn main:app)(\s|\"|$)")


def _commands():
    for name in FILES:
        for number, line in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("command:", "CMD")) and LONG_RUNNING.search(stripped):
                yield f"{name}:{number}", stripped


@pytest.mark.parametrize("where, command", list(_commands()))
def test_long_running_process_is_exec_ed(where, command):
    process = LONG_RUNNING.search(command).group(1)
    assert f"exec {process}" in command, f"{where}: {command}"


def test_every_stack_is_covered():
    assert {where.split(":")[0] for where, _ in _commands()} == set(FILES)
