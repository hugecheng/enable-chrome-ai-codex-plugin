from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FINAL_SCRIPT = PLUGIN_ROOT / "skills/enable-chrome-ai/scripts/chrome_ai_state.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


final = load_module("chrome_ai_state_under_test", FINAL_SCRIPT)


def upstream_set_all_is_glic_eligible(obj):
    """Frozen reference from lcandy2/enable-chrome-ai main.py blob 332e6c2."""
    modified = False
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "is_glic_eligible" and value != True:  # noqa: E712
                obj[key] = True
                modified = True
            elif isinstance(value, (dict, list)):
                if upstream_set_all_is_glic_eligible(value):
                    modified = True
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                if upstream_set_all_is_glic_eligible(item):
                    modified = True
    return modified


def upstream_transform(state, version):
    modified = upstream_set_all_is_glic_eligible(state)
    if state.get("variations_country") != "us":
        state["variations_country"] = "us"
        modified = True
    if "variations_permanent_consistency_country" in state:
        consistency = state["variations_permanent_consistency_country"]
        if isinstance(consistency, list) and len(consistency) >= 2:
            if consistency[0] != version or consistency[1] != "us":
                consistency[0] = version
                consistency[1] = "us"
                modified = True
    return modified


class ChromeAiStateTests(unittest.TestCase):
    def test_field_transform_matches_frozen_upstream_main_py_logic(self):
        version = "151.0.7922.138"
        cases = [
            {
                "variations_country": "cn",
                "variations_permanent_consistency_country": ["old", "cn", "tail"],
                "feature": {"is_glic_eligible": False},
            },
            {
                "variations_country": "hk",
                "feature": [{"is_glic_eligible": "false"}, {"nested": True}],
            },
            {
                "variations_country": "us",
                "variations_permanent_consistency_country": "invalid",
                "feature": {"is_glic_eligible": 1},
            },
            {
                "variations_country": "us",
                "variations_permanent_consistency_country": [version, "us"],
                "feature": {"is_glic_eligible": True},
            },
        ]

        for original in cases:
            with self.subTest(original=original):
                expected = copy.deepcopy(original)
                expected_modified = upstream_transform(expected, version)
                actual = copy.deepcopy(original)
                modified = final.apply_upstream_patch(actual, version)
                self.assertEqual(actual, expected)
                self.assertEqual(modified, expected_modified)

    def test_apply_backup_atomic_write_and_restore_round_trip(self):
        version = "151.0.7922.138"
        original = {
            "variations_country": "cn",
            "variations_permanent_consistency_country": ["old", "cn", "tail"],
            "feature": {"is_glic_eligible": False},
        }

        with tempfile.TemporaryDirectory() as directory:
            user_data = Path(directory) / "Chrome"
            user_data.mkdir()
            (user_data / "Last Version").write_text(version, encoding="utf-8")
            state_file = user_data / "Local State"
            state_file.write_text(json.dumps(original), encoding="utf-8")
            state_file.chmod(0o600)

            channels = {"stable": str(user_data)}
            with (
                mock.patch.object(final, "get_version_and_user_data_path", return_value=channels),
                mock.patch.object(final, "shutdown_chrome", return_value=set()),
                mock.patch.object(final, "restart_chrome"),
            ):
                applied = final.command_apply()
                result = applied["channels"][0]
                self.assertEqual(result["status"], "patched")
                backup = Path(result["backup"])
                self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), original)
                if os.name == "nt":
                    self.assertTrue(backup.stat().st_mode & stat.S_IWUSR)
                else:
                    self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)

                patched = final.load_json_object(state_file)
                self.assertEqual(patched["variations_country"], "us")
                self.assertEqual(
                    patched["variations_permanent_consistency_country"],
                    [version, "us", "tail"],
                )
                self.assertTrue(patched["feature"]["is_glic_eligible"])
                if os.name == "nt":
                    self.assertTrue(state_file.stat().st_mode & stat.S_IWUSR)
                else:
                    self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)

                restored = final.command_restore(str(backup))
                self.assertEqual(restored["channel"], "stable")
                self.assertEqual(final.load_json_object(state_file), original)
                self.assertTrue(Path(restored["safety_backup"]).is_file())

    def test_summary_uses_upstream_transform_as_patch_decision(self):
        version = "151.0.7922.138"
        stale = {
            "variations_country": "us",
            "variations_permanent_consistency_country": ["old", "us"],
            "a": {"is_glic_eligible": True},
            "b": {"is_glic_eligible": "false"},
        }
        summary = final.state_summary(stale, version)
        self.assertTrue(summary["needs_patch"])
        self.assertEqual(summary["is_glic_eligible"]["upstream_non_true_count"], 1)

    def test_unchanged_state_does_not_create_backup(self):
        version = "151.0.7922.138"
        state = {
            "variations_country": "us",
            "variations_permanent_consistency_country": [version, "us", "tail"],
            "feature": {"is_glic_eligible": True},
        }

        with tempfile.TemporaryDirectory() as directory:
            user_data = Path(directory) / "Chrome"
            user_data.mkdir()
            state_file = user_data / "Local State"
            state_file.write_text(json.dumps(state), encoding="utf-8")

            result = final.patch_local_state(user_data, version)

            self.assertEqual(result["status"], "unchanged")
            self.assertIsNone(result["backup"])
            self.assertFalse(final.backup_directory(user_data).exists())

    def test_chrome_restarts_when_operation_fails(self):
        error = RuntimeError("write failed")
        with (
            mock.patch.object(final, "shutdown_chrome", return_value={"/chrome"}),
            mock.patch.object(final, "restart_chrome") as restart,
        ):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                final.run_with_chrome_stopped(
                    lambda: (_ for _ in ()).throw(error)
                )

        restart.assert_called_once_with({"/chrome"})

    def test_backup_validation_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as directory:
            user_data = Path(directory) / "Chrome"
            backup_dir = final.backup_directory(user_data)
            backup_dir.mkdir(parents=True)
            invalid = backup_dir / "Local State.invalid.bak"
            invalid.write_text("[]", encoding="utf-8")

            with mock.patch.object(
                final,
                "get_version_and_user_data_path",
                return_value={"stable": str(user_data)},
            ):
                with self.assertRaises(ValueError):
                    final.validated_backup(str(invalid))

    def test_fsync_file_uses_read_write_descriptor(self):
        path = Path("backup.bak")
        with (
            mock.patch.object(final.os, "open", return_value=42) as open_file,
            mock.patch.object(final.os, "fsync") as fsync,
            mock.patch.object(final.os, "close") as close,
        ):
            final.fsync_file(path)

        open_file.assert_called_once_with(path, final.os.O_RDWR)
        fsync.assert_called_once_with(42)
        close.assert_called_once_with(42)

    def test_restore_rejects_backup_outside_channel_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_data = root / "Chrome"
            user_data.mkdir()
            outside = root / "Local State.outside.bak"
            outside.write_text("{}", encoding="utf-8")
            with mock.patch.object(
                final,
                "get_version_and_user_data_path",
                return_value={"stable": str(user_data)},
            ):
                with self.assertRaises(ValueError):
                    final.validated_backup(str(outside))


if __name__ == "__main__":
    unittest.main()
