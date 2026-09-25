"""Fail-closed Linux command sandbox. No host-shell or unsandboxed fallback."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from contextlib import suppress
from pathlib import Path, PurePosixPath

from pydantic import Field

from ml_analyser.agent.models import StrictModel


class SandboxError(ValueError):
    """Execution failed or containment is unavailable."""


class ResourceLimits(StrictModel):
    timeout_seconds: int = Field(default=10, ge=1, le=120)
    memory_mb: int = Field(default=512, ge=64, le=2048)
    cpu_seconds: int = Field(default=10, ge=1, le=120)
    output_bytes: int = Field(default=65536, ge=1024, le=1048576)
    processes: int = Field(default=16, ge=1, le=64)


def safe_path(root: Path, relative: str, *, exists: bool = True) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or ":" in relative
    ):
        raise SandboxError("path must be relative and cannot contain traversal")
    target = root / relative
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise SandboxError("symlink paths are not permitted")
    resolved = target.resolve(strict=exists)
    if not resolved.is_relative_to(root.resolve()):
        raise SandboxError("path escapes workspace")
    return resolved


def sandbox_available() -> bool:
    return sys.platform == "linux" and shutil.which("bwrap") is not None


def sandbox_command(
    root: Path,
    command: list[str],
    cwd: str,
    outputs: list[str],
    environment: dict[str, str],
    limits: ResourceLimits,
) -> list[str]:
    executable = shutil.which("bwrap")
    if not sandbox_available() or executable is None:
        raise SandboxError("generic execution requires Linux bubblewrap; preview only on this host")
    argv = [
        executable,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
    ]
    for path in ("/bin", "/lib", "/lib64"):
        if Path(path).exists():
            argv.extend(["--ro-bind", path, path])
    argv.extend(["--proc", "/proc", "--dev", "/dev", "--ro-bind", str(root), "/work"])
    for relative in outputs:
        target = safe_path(root, relative, exists=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(b"")
        argv.extend(["--bind", str(target), f"/work/{relative}"])
    for key, value in sorted(environment.items()):
        argv.extend(["--setenv", key, value])
    safe_path(root, cwd)
    launcher = Path(__file__).with_name("sandbox_limits.py")
    argv.extend(
        [
            "--ro-bind",
            str(launcher),
            "/sandbox_limits.py",
            "--chdir",
            f"/work/{cwd}",
            "--",
            "/usr/bin/python3",
            "-I",
            "/sandbox_limits.py",
            str(limits.memory_mb),
            str(limits.cpu_seconds),
            str(limits.output_bytes),
            str(limits.processes),
            *command,
        ]
    )
    return argv


def run_sandbox(
    root: Path,
    command: list[str],
    cwd: str,
    outputs: list[str],
    environment: dict[str, str],
    limits: ResourceLimits,
) -> str:
    argv = sandbox_command(root, command, cwd, outputs, environment, limits)
    # Set process caps inside the new user namespace, after sandbox setup.
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin"},
        start_new_session=True,
    )
    chunks: list[bytes] = []
    errors: list[bytes] = []
    overflow = threading.Event()

    def capture() -> None:
        assert process.stdout is not None
        data = process.stdout.read(limits.output_bytes + 1)
        chunks.append(data)
        if len(data) > limits.output_bytes:
            overflow.set()
            process.kill()

    def drain_errors() -> None:
        assert process.stderr is not None
        data = process.stderr.read(limits.output_bytes + 1)
        errors.append(data[:1000])
        if len(data) > limits.output_bytes:
            overflow.set()
            process.kill()

    threads = [threading.Thread(target=capture), threading.Thread(target=drain_errors)]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=limits.timeout_seconds)
    except subprocess.TimeoutExpired as error:
        raise SandboxError("benchmark timeout") from error
    finally:
        if sys.platform == "linux":
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        for thread in threads:
            thread.join(timeout=2)
    if overflow.is_set():
        raise SandboxError("benchmark output limit exceeded")
    if process.returncode:
        detail = b"".join(errors).decode("utf-8", errors="replace")[:1000]
        raise SandboxError(f"benchmark exited with code {process.returncode}: {detail}")
    return b"".join(chunks).decode("utf-8", errors="strict")
