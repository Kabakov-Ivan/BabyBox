"""Interactive shell for the developer panel (SSH-style console on-device)."""

from __future__ import annotations

import os
import pty
import select
import signal
import subprocess
import threading
from collections import deque
from typing import Any

# Hardcoded device credentials — used by the panel, never prompted in UI.
SSH_USER = "admin"
SSH_PASSWORD = "2376"

_lock = threading.Lock()
_proc: subprocess.Popen[Any] | None = None
_master_fd: int | None = None
_buffer: deque[str] = deque(maxlen=4000)
_reader: threading.Thread | None = None
_alive = False
_target = "127.0.0.1"


def _append(text: str) -> None:
    if not text:
        return
    _buffer.append(text)


def _reader_loop(fd: int) -> None:
    global _alive
    while _alive:
        try:
            ready, _, _ = select.select([fd], [], [], 0.35)
        except (ValueError, OSError):
            break
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        _append(chunk.decode("utf-8", errors="replace"))
    _alive = False
    _append("\n[сессия завершена]\n")


def status() -> dict[str, Any]:
    with _lock:
        running = bool(_proc is not None and _proc.poll() is None and _alive)
        return {
            "connected": running,
            "user": SSH_USER,
            "host": _target,
            "target": f"{SSH_USER}@{_target}",
        }


def read_output(clear: bool = True) -> str:
    with _lock:
        if not _buffer:
            return ""
        text = "".join(_buffer)
        if clear:
            _buffer.clear()
        return text


def stop() -> dict[str, Any]:
    global _proc, _master_fd, _reader, _alive
    with _lock:
        _alive = False
        proc = _proc
        fd = _master_fd
        _proc = None
        _master_fd = None
        _reader = None
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=1.5)
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    return status()


def start(host: str | None = None) -> dict[str, Any]:
    """Open an interactive login shell as the BabyBox service user (admin)."""
    global _proc, _master_fd, _reader, _alive, _target
    stop()
    _target = (host or "127.0.0.1").strip() or "127.0.0.1"
    master, slave = pty.openpty()
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["HISTCONTROL"] = "ignoredups"
    shell = env.get("SHELL") or "/bin/bash"
    home = str(os.path.expanduser("~") or f"/home/{SSH_USER}")

    try:
        proc = subprocess.Popen(
            [shell, "-l"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            cwd=home if os.path.isdir(home) else "/",
            preexec_fn=os.setsid,
            close_fds=True,
        )
    except OSError as error:
        try:
            os.close(master)
        except OSError:
            pass
        try:
            os.close(slave)
        except OSError:
            pass
        raise RuntimeError(f"Не удалось запустить консоль: {error}") from error

    try:
        os.close(slave)
    except OSError:
        pass

    with _lock:
        _proc = proc
        _master_fd = master
        _alive = True
        _buffer.clear()
        _append(f"[ssh] {SSH_USER}@{_target}  (локальная сессия устройства)\n")
        _reader = threading.Thread(target=_reader_loop, args=(master,), daemon=True)
        _reader.start()
    return status()


def write(data: str) -> dict[str, Any]:
    if not isinstance(data, str):
        raise ValueError("Пустой ввод")
    with _lock:
        fd = _master_fd
        running = bool(_proc is not None and _proc.poll() is None and _alive)
    if not running or fd is None:
        raise RuntimeError("SSH-сессия не подключена")
    payload = data if data.endswith("\n") or data.endswith("\r") else data + "\n"
    os.write(fd, payload.encode("utf-8", errors="replace"))
    return status()
