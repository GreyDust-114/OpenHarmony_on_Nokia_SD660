"""Kernel-only GitHub Actions builder; the default invocation prints a plan.

No ADB, flashing, boot-image packaging, releases, secrets, or full OH checkout.
Execution requires --execute, Linux and the GitHub Actions environment. External
kernel code is compiled only on the disposable runner at a fixed git commit.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
TARGETS_FILE = PROJECT / "ci/kernel-targets.json"
ALLOWED_REPOSITORIES = {
    "https://github.com/nokia-msm8998/android_kernel_nokia_sdm660.git",
    "https://github.com/eclipse-oniro-mirrors/kernel_linux_6.6.git",
}
ALLOWED_DEPENDENCY_REPOSITORIES = {
    "https://github.com/eclipse-oniro-mirrors/kernel_linux_common_modules.git",
}


def relative_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError(f"Unsafe relative source path: {value!r}")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError(f"Unexpected source path: {value!r}")
    return value


def load_targets() -> dict:
    data = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported target schema")
    targets = data["targets"]
    for name, target in targets.items():
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Invalid target name")
        if target["repository"] not in ALLOWED_REPOSITORIES:
            raise ValueError("Kernel source repository is not allow-listed")
        if not re.fullmatch(r"[a-f0-9]{40}", target["commit"]):
            raise ValueError("Kernel source must be pinned to a full commit")
        for path in [target["defconfig"], *target["fragments"], target["image_target"]]:
            relative_path(path)
        for path in (target.get("patch"), target.get("object_target")):
            if path:
                relative_path(path)
        for dtb in target.get("dtb_targets", []):
            if not re.fullmatch(r"qcom/[A-Za-z0-9_-]+\.dtb", dtb):
                raise ValueError("Invalid DTB target")
        for dtb, profile in target.get("dtb_profiles", {}).items():
            if dtb not in target.get("dtb_targets", []) or profile != "b2n-touch":
                raise ValueError("Invalid compiled-DTB contract")
        for patch in target.get("support_patches", []) + ([target["board_patch"]] if target.get("board_patch") else []):
            relative_path(patch["path"])
            if not re.fullmatch(r"[a-f0-9]{64}", patch["sha256"]):
                raise ValueError("Support patch must have a pinned SHA256")
        for symbol in target.get("disable_symbols", []):
            if not re.fullmatch(r"[A-Z0-9_]+", symbol):
                raise ValueError("Invalid Kconfig disable symbol")
        for symbol in target["enable_symbols"]:
            if not re.fullmatch(r"[A-Z0-9_]+", symbol):
                raise ValueError("Invalid Kconfig symbol")
        if target["toolchain"] not in ("legacy-clang14-gnu-binutils", "llvm14"):
            raise ValueError("Unknown toolchain")
        if not isinstance(target.get("keep_going_on_compile_error", False), bool):
            raise ValueError("keep_going_on_compile_error must be a boolean")
        seen_dependencies = set()
        for dependency in target.get("source_dependencies", []):
            name = dependency["name"]
            if not re.fullmatch(r"[a-z0-9-]+", name) or name in seen_dependencies:
                raise ValueError("Invalid/duplicate dependency name")
            seen_dependencies.add(name)
            if dependency["repository"] not in ALLOWED_DEPENDENCY_REPOSITORIES:
                raise ValueError("Dependency repository is not allow-listed")
            if not re.fullmatch(r"[a-f0-9]{40}", dependency["commit"]):
                raise ValueError("Dependency must be pinned to a full commit")
            for overlay in dependency["overlays"]:
                relative_path(overlay["source"])
                relative_path(overlay["destination"])
    return targets


def make_command(target: dict, output: str) -> list[str]:
    command = ["make", f"O={output}", "ARCH=arm64", "CROSS_COMPILE=aarch64-linux-gnu-", "HOSTCC=gcc", "HOSTCXX=g++"]
    if target["toolchain"] == "legacy-clang14-gnu-binutils":
        command += ["CC=clang-14", "CLANG_TRIPLE=aarch64-linux-gnu-",
                    "CROSS_COMPILE_ARM32=arm-linux-gnueabi-", "CROSS_COMPILE_COMPAT=arm-linux-gnueabi-"]
    else:
        command += ["LLVM=-14", "LLVM_IAS=1"]
    return command


def build_plan(target: dict, output: str, jobs: int) -> list[dict]:
    if jobs not in (1, 2, 3, 4):
        raise ValueError("Jobs must be between 1 and 4")
    base = make_command(target, output)
    steps = [{"label": "configure-base", "command": base + [target["defconfig"]]}]
    if target["fragments"]:
        steps.append({"label": "merge-device-config", "command": ["bash", "scripts/kconfig/merge_config.sh", "-m",
                      "-O", output, str(Path(output) / ".config"),
                      *["arch/arm64/configs/" + p for p in target["fragments"]]]})
    for symbol in target["enable_symbols"]:
        steps.append({"label": "enable-" + symbol.lower(), "command": ["bash", "scripts/config", "--file",
                      str(Path(output) / ".config"), "--enable", symbol]})
    for symbol in target.get("disable_symbols", []):
        steps.append({"label": "disable-" + symbol.lower(), "command": ["bash", "scripts/config", "--file",
                      str(Path(output) / ".config"), "--disable", symbol]})
    steps.append({"label": "resolve-config", "command": base + ["olddefconfig"]})
    if target.get("dtb_targets"):
        steps.append({"label": "compile-device-trees", "command": base + [f"-j{jobs}", *target["dtb_targets"]]})
    if target.get("object_target"):
        steps.append({"label": "compile-ft8716-object", "command": base + [f"-j{jobs}", target["object_target"]]})
    compile_flags = (["-k"] if target.get("keep_going_on_compile_error", False) else []) + [f"-j{jobs}"]
    steps.append({"label": "compile-kernel", "command": base + compile_flags + [target["image_target"]]})
    return steps


def check_required_config(source: str, required: list[str], required_disabled: list[str] | None = None) -> None:
    actual = set(source.splitlines())
    missing = [line for line in required if line not in actual]
    missing_disabled = [line for line in (required_disabled or []) if line not in actual]
    if missing or missing_disabled:
        raise ValueError("Required kernel configuration was not retained: " + ", ".join(missing + missing_disabled))


def materialize_dependencies(kernel: Path, roots: dict[str, Path], dependencies: list[dict]) -> list[dict]:
    """Populate explicit external module paths before Kconfig, without stubs/deletes.

    Upstream common_modules apply scripts link these module contents into the
    same paths. Copying the complete pinned subtrees keeps this small standalone
    build independent of the full OH checkout and is testable without symlinks.
    """
    applied = []
    for dependency in dependencies:
        root = roots[dependency["name"]]
        for overlay in dependency["overlays"]:
            source = root / relative_path(overlay["source"])
            dest = kernel / relative_path(overlay["destination"])
            if not (source / "Kconfig").is_file():
                raise FileNotFoundError(f"Missing external Kconfig source: {source}")
            if not source.resolve().is_relative_to(root.resolve()) or source.is_symlink():
                raise ValueError("Dependency source escapes its checkout")
            if dest.exists() or dest.is_symlink():
                raise RuntimeError(f"Refusing to replace existing kernel module path: {dest}")
            if not dest.parent.resolve().is_relative_to(kernel.resolve()):
                raise ValueError("Dependency destination escapes kernel checkout")
            if any(p.is_symlink() for p in source.rglob("*")):
                raise ValueError("Unexpected symlink in external module subtree")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, dest)
            applied.append({"dependency": dependency["name"], **overlay})
    return applied


def collect_device_trees(target: dict, source: Path, output: Path, artifacts: Path) -> dict:
    from device_tree import inspect_dtb

    result = {}
    for name in target.get("dtb_targets", []):
        relative_path(name)
        compiled = output / "arch/arm64/boot/dts" / name
        if not compiled.is_file() or not 40 <= compiled.stat().st_size <= 16 * 1024**2:
            raise ValueError("Missing or oversized compiled DTB: " + name)
        dest = artifacts / "research-device-trees" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(compiled, dest)
        dts = Path(name).with_suffix(".dts")
        saved = artifacts / "device-tree-sources" / dts
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "arch/arm64/boot/dts" / dts, saved)
    # Preserve the complete diagnostic inputs even if a semantic check fails.
    for name in target.get("dtb_targets", []):
        result[name] = inspect_dtb(output / "arch/arm64/boot/dts" / name,
                                   target.get("dtb_profiles", {}).get(name))
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(name: str, target: dict, work: Path, jobs: int) -> None:
    if sys.platform != "linux" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("--execute is restricted to a Linux GitHub Actions runner; use plan mode locally")
    source, output, artifacts = work / "source", work / "out", work / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    if source.exists() or output.exists() or (work / "dependencies").exists():
        raise RuntimeError("Source/output directory already exists; refusing to overwrite or delete it")
    source.mkdir()
    logs = artifacts / "logs"
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(ARCH="arm64", GIT_TERMINAL_PROMPT="0", KBUILD_BUILD_USER="builder",
               KBUILD_BUILD_HOST="github-actions", KBUILD_BUILD_VERSION="1")
    provenance = {"target": name, **target, "jobs": jobs, "status": "running", "stage": "preflight",
        "workflow_commit": os.environ.get("GITHUB_SHA"), "workflow_ref": os.environ.get("GITHUB_REF"),
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "warning": "Research kernel/DTB outputs; no boot.img or complete phone system. No runtime testing. Do not flash."}
    (artifacts / "DO-NOT-FLASH.txt").write_text(provenance["warning"] + "\n", encoding="utf-8")
    shutil.copyfile(TARGETS_FILE, artifacts / "kernel-targets.json")
    plan = build_plan(target, str(output), jobs)
    (artifacts / "build-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    counter = 0

    def run(command: list[str], label: str) -> str:
        nonlocal counter
        counter += 1
        provenance["stage"] = label
        filename = logs / f"{counter:02d}-{label}.log"
        print("+ " + shlex.join(command), flush=True)
        with filename.open("w", encoding="utf-8") as log:
            log.write("$ " + shlex.join(command) + "\n")
            log.flush()
            process = subprocess.Popen(command, cwd=source, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            captured = []
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                if label in ("verify-source", "source-epoch") or label.startswith("verify-dependency-"):
                    captured.append(line)
            code = process.wait()
        if code:
            raise subprocess.CalledProcessError(code, command)
        return "".join(captured).strip()

    try:
        free = shutil.disk_usage(work).free
        provenance["preflight_free_bytes"] = free
        if free < 8 * 1024**3:
            raise RuntimeError("Less than 8 GiB free before source fetch; no broad runner cleanup attempted")
        run(["clang-14", "--version"], "clang-version")
        run(["aarch64-linux-gnu-gcc", "--version"], "cross-gcc-version")
        run(["aarch64-linux-gnu-ld", "--version"], "binutils-version")
        run(["dpkg-query", "-W", "clang-14", "llvm-14", "lld-14", "gcc-aarch64-linux-gnu",
             "gcc-arm-linux-gnueabi"], "toolchain-packages")
        run(["git", "init", "."], "init-source")
        run(["git", "remote", "add", "origin", target["repository"]], "set-source")
        run(["git", "-c", "protocol.version=2", "fetch", "--depth=1", "origin", target["commit"]], "fetch-source")
        run(["git", "checkout", "--detach", "FETCH_HEAD"], "checkout-source")
        head = run(["git", "rev-parse", "HEAD"], "verify-source")
        if head != target["commit"]:
            raise RuntimeError("Source commit verification failed")
        epoch = int(run(["git", "show", "-s", "--format=%ct", "HEAD"], "source-epoch"))
        env["SOURCE_DATE_EPOCH"] = str(epoch)
        env["KBUILD_BUILD_TIMESTAMP"] = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%a %b %d %H:%M:%S UTC %Y")
        provenance["source_date_epoch"] = epoch
        dependency_roots = {}
        for dependency in target.get("source_dependencies", []):
            name = dependency["name"]
            directory = work / "dependencies" / name
            directory.mkdir(parents=True)
            prefix = ["git", "-C", str(directory)]
            run(prefix + ["init", "."], "init-" + name)
            run(prefix + ["remote", "add", "origin", dependency["repository"]], "set-" + name)
            run(prefix + ["-c", "protocol.version=2", "fetch", "--depth=1", "origin", dependency["commit"]], "fetch-" + name)
            run(prefix + ["checkout", "--detach", "FETCH_HEAD"], "checkout-" + name)
            actual = run(prefix + ["rev-parse", "HEAD"], "verify-dependency-" + name)
            if actual != dependency["commit"]:
                raise RuntimeError("Dependency commit verification failed: " + name)
            dependency_roots[name] = directory
            licenses = artifacts / "dependency-licenses"
            licenses.mkdir(exist_ok=True)
            if (directory / "LICENSE").is_file():
                shutil.copyfile(directory / "LICENSE", licenses / (name + "-LICENSE"))
        provenance["stage"] = "prepare-external-kconfig"
        applied = materialize_dependencies(source, dependency_roots, target.get("source_dependencies", []))
        if applied:
            (artifacts / "source-dependencies.json").write_text(json.dumps({"inputs": target["source_dependencies"],
                "materialized_paths": applied}, indent=2) + "\n", encoding="utf-8")
        patches = target.get("support_patches", []) + ([target["board_patch"]] if target.get("board_patch") else [])
        for index, spec in enumerate(patches, 1):
            patch = PROJECT / spec["path"]
            digest = sha256(patch)
            if digest != spec["sha256"]:
                raise ValueError("Support patch checksum mismatch: " + spec["path"])
            provenance.setdefault("support_patch_sha256s", {})[spec["path"]] = digest
            saved = artifacts / "support-patches"
            saved.mkdir(exist_ok=True)
            shutil.copyfile(patch, saved / patch.name)
            run(["git", "apply", "--check", str(patch)], f"check-support-patch-{index}")
            run(["git", "apply", str(patch)], f"apply-support-patch-{index}")
        if target.get("patch"):
            patch = PROJECT / target["patch"]
            provenance["patch_sha256"] = sha256(patch)
            shutil.copyfile(patch, artifacts / "applied-review.patch")
            run(["git", "apply", "--check", str(patch)], "check-review-patch")
            run(["git", "apply", str(patch)], "apply-review-patch")
        base_config = source / "arch/arm64/configs" / target["defconfig"]
        if not base_config.is_file():
            raise FileNotFoundError(f"Missing defconfig: {base_config}")
        for fragment in target["fragments"]:
            if not (source / "arch/arm64/configs" / fragment).is_file():
                raise FileNotFoundError(f"Missing fragment: {fragment}")
        for step in plan:
            run(step["command"], step["label"])
            if step["label"] == "compile-device-trees":
                provenance["stage"] = "validate-device-trees"
                provenance["device_trees"] = collect_device_trees(target, source, output, artifacts)
                (artifacts / "device-tree-validation.json").write_text(
                    json.dumps(provenance["device_trees"], indent=2) + "\n", encoding="utf-8")
            if step["label"] == "resolve-config":
                check_required_config((output / ".config").read_text(), target["required_symbols"],
                                      target.get("required_disabled_symbols", []))
        image = output / "arch/arm64/boot" / target["image_target"]
        if not image.is_file() or image.stat().st_size == 0:
            raise RuntimeError("Build returned success but the expected kernel image is absent/empty")
        images = artifacts / "research-kernel-not-a-boot-image"
        images.mkdir()
        shutil.copyfile(image, images / image.name)
        provenance["kernel_image_sha256"] = sha256(image)
        provenance["kernel_image_bytes"] = image.stat().st_size
        provenance["status"] = "compiled-not-runtime-tested"
    except Exception as exc:
        provenance.update(status="failed", error=str(exc))
        raise
    finally:
        for name_on_disk in (".config", "System.map"):
            if (output / name_on_disk).is_file():
                shutil.copyfile(output / name_on_disk, artifacts / ("kernel.config" if name_on_disk == ".config" else name_on_disk))
        if (source / "COPYING").is_file():
            shutil.copyfile(source / "COPYING", artifacts / "KERNEL-COPYING")
        provenance["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (artifacts / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        lines = []
        for path in sorted(artifacts.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                lines.append(f"{sha256(path)}  {path.relative_to(artifacts).as_posix()}")
        (artifacts / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as file:
                file.write(f"## {name}\n\nStatus: `{provenance['status']}`; last stage: `{provenance['stage']}`.\n\n"
                           "Research output only; no flashing or runtime validation. See provenance and logs in the artifact.\n")


def main() -> None:
    targets = load_targets()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(targets), default="nokia44-baseline")
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--execute", action="store_true", help="Run only on the Linux GitHub-hosted runner")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    target = targets[args.target]
    if not args.execute:
        print(json.dumps({"target": args.target, **target, "steps": build_plan(target, "OUT", args.jobs),
                          "execution": "not_requested"}, indent=2))
        return
    if not args.work_dir:
        parser.error("--execute requires --work-dir")
    execute(args.target, target, args.work_dir.resolve(), args.jobs)


if __name__ == "__main__":
    main()
