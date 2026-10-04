import io
import subprocess
import tarfile
from pathlib import Path

import pytest

import docker

ENTRY = Path(__file__).resolve().parents[1] / "docker" / "entrypoint.sh"


@pytest.fixture(scope="module")
def entrypoint_container():
    """The production target is Linux Docker, even when pytest runs on Windows.

    Use the same image already required by the PostgreSQL fixtures. No host shell,
    grep, executable permission bits, bind mounts or host PATH conventions are needed.
    A missing Docker daemon is an error, not a reason to skip these checks.
    """
    client = docker.from_env(timeout=10)
    container = None
    try:
        container = client.containers.run(
            "postgres:16-alpine",
            entrypoint=["/bin/sh"],
            command=["-c", "sleep 600"],
            detach=True,
            network_disabled=True,
        )
        yield container
    finally:
        if container is not None:
            container.remove(force=True)
        client.close()


def _run(container, args, env_extra=None, *, at_head=False):
    """Copy real entrypoint bytes and isolated stubs through Docker's Python API."""
    files = {"entrypoint.sh": ENTRY.read_bytes()}
    for name in ("alembic", "uvicorn"):
        script = f'#!/bin/sh\necho "RAN {name} args=$* db=$DATABASE_URL"\n'
        if name == "alembic" and at_head:
            script = '#!/bin/sh\necho "0017_meet (head)"\n'
        files[f"bin/{name}"] = script.encode("utf-8")
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(f"entrypoint-test/{name}")
            info.size = len(content)
            info.mode = 0o755  # Linux container permissions, never host chmod.
            tar.addfile(info, io.BytesIO(content))
    assert container.put_archive("/tmp", archive.getvalue())
    env = {"PATH": "/tmp/entrypoint-test/bin:/usr/local/bin:/usr/bin:/bin"}
    if env_extra:
        env.update(env_extra)
    command = ["/bin/sh", "/tmp/entrypoint-test/entrypoint.sh", *args]
    result = container.exec_run(command, environment=env)
    output = result.output.decode("utf-8")
    assert result.exit_code == 0, output
    return subprocess.CompletedProcess(command, result.exit_code, stdout=output)


def test_migrate_only(entrypoint_container):
    out = _run(entrypoint_container, ["migrate"]).stdout
    assert "RAN alembic args=upgrade head" in out
    assert "RAN uvicorn" not in out


def test_serve_only(entrypoint_container):
    out = _run(entrypoint_container, ["serve"]).stdout
    assert "RAN uvicorn" in out
    assert "RAN alembic" not in out


def test_default_runs_both(entrypoint_container):
    out = _run(entrypoint_container, []).stdout
    assert "RAN alembic args=upgrade head" in out
    assert "RAN uvicorn" in out


def test_assembles_database_url_from_parts(entrypoint_container):
    out = _run(
        entrypoint_container,
        ["serve"],
        {
            "DB_HOST": "pg",
            "DB_USER": "ic",
            "DB_PASSWORD": "secret",
            "DB_NAME": "icdb",
        },
    ).stdout
    assert "db=postgresql+psycopg://ic:secret@pg:5432/icdb" in out


def test_preserves_explicit_database_url(entrypoint_container):
    out = _run(
        entrypoint_container,
        ["serve"],
        {
            "DATABASE_URL": "postgresql+psycopg://x:y@host:5432/d",
            "DB_HOST": "ignored",
            "DB_USER": "ignored",
            "DB_PASSWORD": "z",
            "DB_NAME": "ignored",
        },
    ).stdout
    assert "db=postgresql+psycopg://x:y@host:5432/d" in out


def test_await_db_exits_when_at_head(entrypoint_container):
    # The real Linux grep must recognize the head revision and exit promptly.
    r = _run(entrypoint_container, ["await-db"], at_head=True)
    assert r.returncode == 0
    assert "waiting for DB migrations" not in r.stdout
