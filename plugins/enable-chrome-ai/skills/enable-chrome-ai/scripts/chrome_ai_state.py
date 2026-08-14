#!/usr/bin/env python3
"""Manage Chrome AI eligibility using lcandy2/enable-chrome-ai semantics.

The field transformation is intentionally kept equivalent to the upstream
``main.py``. This local wrapper adds backups, atomic writes, full write
verification, restore support, and a non-interactive command-line interface.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, TypeVar

try:
    import psutil
except ModuleNotFoundError:  # The local plugin remains usable without pip installs.
    psutil = None  # type: ignore[assignment]


BACKUP_SUBDIRECTORY = Path("Codex Backups") / "enable-chrome-ai"
T = TypeVar("T")


def get_version_and_user_data_path() -> dict[str, str]:
    """Return installed Chrome channels using the paths from upstream main.py."""
    os_and_user_data_paths = {
        "win32": {
            "stable": "~/AppData/Local/Google/Chrome/User Data",
            "canary": "~/AppData/Local/Google/Chrome SxS/User Data",
            "dev": "~/AppData/Local/Google/Chrome Dev/User Data",
            "beta": "~/AppData/Local/Google/Chrome Beta/User Data",
        },
        "linux": {
            "stable": "~/.config/google-chrome",
            "canary": "~/.config/google-chrome-canary",
            "dev": "~/.config/google-chrome-unstable",
            "beta": "~/.config/google-chrome-beta",
        },
        "darwin": {
            "stable": "~/Library/Application Support/Google/Chrome",
            "canary": "~/Library/Application Support/Google/Chrome Canary",
            "dev": "~/Library/Application Support/Google/Chrome Dev",
            "beta": "~/Library/Application Support/Google/Chrome Beta",
        },
    }

    for platform, version_and_user_data_path in os_and_user_data_paths.items():
        available_version_and_user_data_path: dict[str, str] = {}
        if sys.platform.startswith(platform):
            for version, user_data_path in version_and_user_data_path.items():
                expanded = os.path.abspath(os.path.expanduser(user_data_path))
                if os.path.exists(expanded):
                    available_version_and_user_data_path[version] = expanded
            return available_version_and_user_data_path

    raise RuntimeError(f"Unsupported platform {sys.platform}")


def shutdown_chrome_with_psutil() -> set[str]:
    """Run the upstream process-selection logic through psutil."""
    assert psutil is not None
    terminated_chromes: set[str] = set()
    terminated_processes: list[Any] = []
    for process in psutil.process_iter():
        try:
            if sys.platform == "darwin":
                if not process.name().startswith("Google Chrome"):
                    continue
            elif os.path.splitext(process.name())[0] != "chrome":
                continue
            elif not process.is_running():
                continue
            elif process.parent() is not None and process.parent().name() == process.name():
                continue
            location = process.exe()
            process.kill()
            terminated_chromes.add(location)
            terminated_processes.append(process)
        except psutil.NoSuchProcess:
            pass

    _, alive = psutil.wait_procs(terminated_processes, timeout=10)
    if alive:
        pids = ", ".join(str(process.pid) for process in alive)
        raise RuntimeError(f"Chrome processes did not exit: {pids}")
    return terminated_chromes


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def shutdown_chrome_without_psutil() -> set[str]:
    """macOS/Linux fallback matching the upstream process name filters."""
    if not (sys.platform == "darwin" or sys.platform.startswith("linux")):
        raise RuntimeError("psutil is required to stop Chrome on this platform")

    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,comm="],
        check=True,
        capture_output=True,
        text=True,
    )
    targets: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        pid = int(fields[0])
        executable = fields[1]
        name = Path(executable).name
        if sys.platform == "darwin":
            matches = name.startswith("Google Chrome")
        else:
            matches = os.path.splitext(name)[0] == "chrome"
        if matches:
            targets.append((pid, executable))

    for pid, _ in targets:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and any(pid_exists(pid) for pid, _ in targets):
        time.sleep(0.1)
    alive = [pid for pid, _ in targets if pid_exists(pid)]
    if alive:
        raise RuntimeError("Chrome processes did not exit: " + ", ".join(map(str, alive)))
    return {executable for _, executable in targets}


def shutdown_chrome() -> set[str]:
    """Stop the same Chrome process set targeted by upstream and wait for exit."""
    if psutil is not None:
        return shutdown_chrome_with_psutil()
    return shutdown_chrome_without_psutil()


def restart_chrome(executables: set[str]) -> None:
    """Restart every executable recorded by the upstream shutdown method."""
    errors: list[str] = []
    for chrome in sorted(executables):
        try:
            subprocess.Popen(
                [chrome],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            errors.append(f"{chrome}: {error}")
    if errors:
        raise RuntimeError("Failed to restart Chrome: " + "; ".join(errors))


def get_last_version(user_data_path: str | Path) -> str | None:
    last_version_file = Path(user_data_path) / "Last Version"
    if not last_version_file.exists():
        return None
    return last_version_file.read_text(encoding="utf-8")


def set_all_is_glic_eligible(obj: Any) -> bool:
    """Recursively find and set all is_glic_eligible to true (upstream logic)."""
    modified = False
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "is_glic_eligible" and value != True:  # noqa: E712 - upstream equality
                obj[key] = True
                modified = True
            elif isinstance(value, (dict, list)):
                if set_all_is_glic_eligible(value):
                    modified = True
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)) and set_all_is_glic_eligible(item):
                modified = True
    return modified


def apply_upstream_patch(local_state: dict[str, Any], last_version: str) -> bool:
    """Apply only the three mutations performed by upstream patch_local_state."""
    modified = set_all_is_glic_eligible(local_state)

    if local_state.get("variations_country") != "us":
        local_state["variations_country"] = "us"
        modified = True

    consistency = local_state.get("variations_permanent_consistency_country")
    if isinstance(consistency, list) and len(consistency) >= 2:
        if consistency[0] != last_version or consistency[1] != "us":
            consistency[0] = last_version
            consistency[1] = "us"
            modified = True

    return modified


def local_state_path(user_data_path: str | Path) -> Path:
    return Path(user_data_path) / "Local State"


def backup_directory(user_data_path: str | Path) -> Path:
    return Path(user_data_path) / BACKUP_SUBDIRECTORY


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def fsync_directory(directory: Path) -> None:
    """Persist a rename on platforms that allow directories to be fsynced."""
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def fsync_file(path: Path) -> None:
    """Flush a completed file through a descriptor valid on Windows and POSIX."""
    descriptor = os.open(path, os.O_RDWR)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON beside the target, fsync it, then atomically replace the target."""
    original_stat = path.stat()
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, stat.S_IMODE(original_stat.st_mode))
        os.replace(temp_path, path)
        temp_path = None
        fsync_directory(path.parent)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def backup_local_state(user_data_path: str | Path, label: str) -> Path:
    source = local_state_path(user_data_path)
    destination_directory = backup_directory(user_data_path)
    destination_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = destination_directory / f"Local State.{label}.{timestamp}.bak"
    shutil.copy2(source, destination)
    os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
    fsync_file(destination)
    load_json_object(destination)
    fsync_directory(destination_directory)
    return destination


def collect_is_glic_values(value: Any, result: list[Any] | None = None) -> list[Any]:
    if result is None:
        result = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "is_glic_eligible":
                result.append(child)
            elif isinstance(child, (dict, list)):
                collect_is_glic_values(child, result)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                collect_is_glic_values(child, result)
    return result


def state_summary(state: dict[str, Any], last_version: str | None) -> dict[str, Any]:
    values = collect_is_glic_values(state)
    preview = copy.deepcopy(state)
    needs_patch = last_version is not None and apply_upstream_patch(preview, last_version)
    return {
        "variations_country": state.get("variations_country"),
        "variations_permanent_consistency_country": state.get(
            "variations_permanent_consistency_country"
        ),
        "is_glic_eligible": {
            "count": len(values),
            "upstream_true_count": sum(value == True for value in values),  # noqa: E712
            "upstream_non_true_count": sum(value != True for value in values),  # noqa: E712
        },
        "needs_patch": needs_patch,
    }


def patch_local_state(user_data_path: str | Path, last_version: str) -> dict[str, Any]:
    """Patch one channel with backup, atomic write, and full-document verification."""
    state_file = local_state_path(user_data_path)
    if not state_file.exists():
        return {"status": "missing", "local_state": str(state_file)}

    original = load_json_object(state_file)
    expected = copy.deepcopy(original)
    modified = apply_upstream_patch(expected, last_version)
    before = state_summary(original, last_version)
    if not modified:
        return {
            "status": "unchanged",
            "local_state": str(state_file),
            "backup": None,
            "before": before,
            "after": before,
        }

    backup = backup_local_state(user_data_path, "before-apply")
    atomic_write_json(state_file, expected)
    verified = load_json_object(state_file)
    if verified != expected:
        raise RuntimeError(
            f"Write verification failed for {state_file}; restore from {backup}"
        )

    return {
        "status": "patched",
        "local_state": str(state_file),
        "backup": str(backup),
        "before": before,
        "after": state_summary(verified, last_version),
    }


def installed_channels() -> dict[str, str]:
    channels = get_version_and_user_data_path()
    if not channels:
        raise RuntimeError("No available user data path found")
    return channels


def command_check() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for channel, user_data_path in installed_channels().items():
        version = get_last_version(user_data_path)
        state_file = local_state_path(user_data_path)
        item: dict[str, Any] = {
            "channel": channel,
            "user_data_path": user_data_path,
            "chrome_version": version,
            "backup_directory": str(backup_directory(user_data_path)),
        }
        if version is None:
            item.update({"status": "missing-version", "needs_patch": None})
        elif not state_file.is_file():
            item.update({"status": "missing-local-state", "needs_patch": None})
        else:
            item.update({"status": "ok", **state_summary(load_json_object(state_file), version)})
        results.append(item)
    return {"platform": sys.platform, "channels": results}


def run_with_chrome_stopped(operation: Callable[[], T]) -> T:
    terminated_chromes = shutdown_chrome()
    operation_error: BaseException | None = None
    try:
        return operation()
    except BaseException as error:
        operation_error = error
        raise
    finally:
        try:
            restart_chrome(terminated_chromes)
        except Exception:
            if operation_error is None:
                raise


def command_apply() -> dict[str, Any]:
    channels = installed_channels()

    def operation() -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for channel, user_data_path in channels.items():
            version = get_last_version(user_data_path)
            if version is None:
                results.append(
                    {
                        "channel": channel,
                        "status": "missing-version",
                        "version_file": str(Path(user_data_path) / "Last Version"),
                    }
                )
                continue
            results.append(
                {
                    "channel": channel,
                    "chrome_version": version,
                    **patch_local_state(user_data_path, version),
                }
            )
        return {"operation": "apply", "channels": results}

    return run_with_chrome_stopped(operation)


def validated_backup(raw_path: str) -> tuple[str, Path, Path]:
    candidate = Path(raw_path).expanduser().resolve()
    for channel, user_data_path in installed_channels().items():
        root = backup_directory(user_data_path).resolve()
        if candidate.parent == root:
            if not candidate.name.startswith("Local State.") or candidate.suffix != ".bak":
                raise ValueError(f"Unrecognized backup name: {candidate.name}")
            if not candidate.is_file():
                raise FileNotFoundError(candidate)
            load_json_object(candidate)
            return channel, Path(user_data_path), candidate
    raise ValueError("Backup is not inside an installed Chrome channel backup directory")


def command_restore(raw_path: str) -> dict[str, Any]:
    channel, user_data_path, selected = validated_backup(raw_path)
    replacement = load_json_object(selected)
    state_file = local_state_path(user_data_path)
    if not state_file.is_file():
        raise FileNotFoundError(state_file)

    def operation() -> dict[str, Any]:
        safety_backup = backup_local_state(user_data_path, "before-restore")
        before = load_json_object(state_file)
        atomic_write_json(state_file, replacement)
        verified = load_json_object(state_file)
        if verified != replacement:
            raise RuntimeError(
                f"Restore verification failed; recover from {safety_backup}"
            )
        version = get_last_version(user_data_path)
        return {
            "operation": "restore",
            "channel": channel,
            "restored_from": str(selected),
            "safety_backup": str(safety_backup),
            "before": state_summary(before, version),
            "after": state_summary(verified, version),
        }

    return run_with_chrome_stopped(operation)


def command_list_backups() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for channel, user_data_path in installed_channels().items():
        version = get_last_version(user_data_path)
        directory = backup_directory(user_data_path)
        backups: list[dict[str, Any]] = []
        if directory.is_dir():
            for path in sorted(directory.glob("Local State.*.bak"), reverse=True):
                try:
                    state = load_json_object(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                backups.append(
                    {
                        "path": str(path.resolve()),
                        "modified_utc": datetime.fromtimestamp(
                            path.stat().st_mtime, timezone.utc
                        ).isoformat(),
                        "summary": state_summary(state, version),
                    }
                )
        results.append(
            {
                "channel": channel,
                "backup_directory": str(directory),
                "backups": backups,
            }
        )
    return {"channels": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Inspect installed Chrome channels without writing")
    subparsers.add_parser("apply", help="Apply the upstream patch with backup and verification")
    subparsers.add_parser("list-backups", help="List validated Local State backups")
    restore = subparsers.add_parser("restore", help="Restore one validated backup")
    restore.add_argument("--backup", required=True, help="Path returned by list-backups")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            result = command_check()
        elif args.command == "apply":
            result = command_apply()
        elif args.command == "list-backups":
            result = command_list_backups()
        else:
            result = command_restore(args.backup)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
