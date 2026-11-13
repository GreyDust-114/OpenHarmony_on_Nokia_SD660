"""Offline CI contract tests. No source downloads, compiler invocation, or phone access."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("kernel_ci_builder", Path(__file__).with_name("build_kernel.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildPlanTests(unittest.TestCase):
    def setUp(self):
        self.targets = builder.load_targets()

    def test_sources_are_pinned_and_allow_listed(self):
        self.assertEqual(set(self.targets), {"nokia44-baseline", "oh66-ft8716"})
        for target in self.targets.values():
            self.assertIn(target["repository"], builder.ALLOWED_REPOSITORIES)
            self.assertRegex(target["commit"], r"^[a-f0-9]{40}$")

    def test_nokia_fragments_order_and_toolchain(self):
        steps = builder.build_plan(self.targets["nokia44-baseline"], "OUT", 2)
        self.assertEqual(steps[0]["command"][-1], "vendor/sdm660-perf_defconfig")
        merge = next(s["command"] for s in steps if s["label"] == "merge-device-config")
        self.assertEqual(merge[-2:], ["arch/arm64/configs/vendor/nokia/nokia.config",
                                    "arch/arm64/configs/vendor/nokia/B2N.config"])
        self.assertIn("CC=clang-14", steps[-1]["command"])
        self.assertIn("CROSS_COMPILE_ARM32=arm-linux-gnueabi-", steps[-1]["command"])
        self.assertEqual(steps[-1]["command"][-1], "Image.gz-dtb")

    def test_modern_plan_compiles_touch_object_before_image(self):
        steps = builder.build_plan(self.targets["oh66-ft8716"], "OUT", 2)
        labels = [s["label"] for s in steps]
        self.assertLess(labels.index("compile-ft8716-object"), labels.index("compile-kernel"))
        self.assertIn("LLVM=-14", steps[-1]["command"])
        self.assertEqual(steps[-1]["command"][-1], "Image.gz")
        self.assertFalse(any("B2N.dtb" in part for s in steps for part in s["command"]))
        self.assertTrue((builder.PROJECT / self.targets["oh66-ft8716"]["patch"]).is_file())

    def test_invalid_parallelism_rejected(self):
        for jobs in (0, 5, 64):
            with self.assertRaises(ValueError):
                builder.build_plan(self.targets["nokia44-baseline"], "OUT", jobs)

    def test_required_config_rejects_silent_kconfig_drop(self):
        builder.check_required_config("CONFIG_TEST=y\n", ["CONFIG_TEST=y"])
        with self.assertRaises(ValueError):
            builder.check_required_config("# CONFIG_TEST is not set\n", ["CONFIG_TEST=y"])

    def test_source_paths_are_not_shell_fragments_or_escapes(self):
        for path in ("../parent", "/absolute", "a/../../b", "a//b", "config;echo", "x\\y"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                builder.relative_path(path)

    def test_default_plan_mode_does_not_create_work_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "must-not-be-created"
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("build_kernel.py")),
                "--target", "oh66-ft8716", "--work-dir", str(work)], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["execution"], "not_requested")
            self.assertFalse(work.exists())

    def test_execution_guard_does_not_touch_local_files(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}):
            work = Path(temp) / "must-not-be-created"
            with self.assertRaises(RuntimeError):
                builder.execute("nokia44-baseline", self.targets["nokia44-baseline"], work, 2)
            self.assertFalse(work.exists())

    def test_low_disk_failure_preserves_metadata_without_running_tools(self):
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": ""}), \
                mock.patch.object(builder.sys, "platform", "linux"), \
                mock.patch.object(builder.shutil, "disk_usage", return_value=mock.Mock(free=1024)), \
                mock.patch.object(builder.subprocess, "Popen") as popen:
            work = Path(temp) / "cloud-work"
            with self.assertRaisesRegex(RuntimeError, "Less than 8 GiB"):
                builder.execute("nokia44-baseline", self.targets["nokia44-baseline"], work, 2)
            popen.assert_not_called()
            report = json.loads((work / "artifacts/provenance.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["stage"], "preflight")
            self.assertTrue((work / "artifacts/SHA256SUMS").is_file())
            self.assertFalse((work / "artifacts/research-kernel-not-a-boot-image").exists())


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = builder.PROJECT / ".github/workflows/kernel-build.yml"
        cls.source = cls.path.read_text(encoding="utf-8")

    def test_manual_only_and_no_self_hosted_runner(self):
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotRegex(self.source, r"(?m)^\s*(push|pull_request|schedule|workflow_run):")
        self.assertIn("runs-on: ubuntu-22.04", self.source)
        self.assertNotIn("self-hosted", self.source)

    def test_actions_pinned_no_extra_secrets_or_write_permission(self):
        uses = re.findall(r"(?m)^\s*uses:\s*(\S+)", self.source)
        self.assertEqual(len(uses), 2)
        self.assertTrue(all(re.search(r"@[a-f0-9]{40}$", item) for item in uses))
        self.assertIn("contents: read", self.source)
        self.assertIn("persist-credentials: false", self.source)
        self.assertNotIn("secrets.", self.source)
        self.assertNotRegex(self.source, r"(?m)^\s*contents:\s*write")

    def test_artifacts_are_bounded_and_collected_on_failure(self):
        self.assertIn("if: always()", self.source)
        self.assertIn("retention-days: 3", self.source)
        self.assertIn("timeout-minutes: 120", self.source)
        self.assertIn("/b2n-kernel/artifacts/", self.source)
        self.assertNotIn("rm -rf", self.source)

    def test_workflow_yaml_if_parser_is_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML absent locally; runner installs python3-yaml")
        data = yaml.load(self.source, Loader=yaml.BaseLoader)
        self.assertEqual(set(data["on"]), {"workflow_dispatch"})
        choices = data["on"]["workflow_dispatch"]["inputs"]["target"]["options"]
        self.assertEqual(set(choices), set(builder.load_targets()))
        self.assertEqual(data["jobs"]["build"]["runs-on"], "ubuntu-22.04")


if __name__ == "__main__":
    unittest.main()
