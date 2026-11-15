"""Regression of real XPM pageflag enum/table guards, not a full kernel build.

The source-contract matrix runs without a compiler. Linux CI additionally
compiles a minimized C harness using the actual enum/macro source for all four
configurations. No tools are installed locally and no phone is accessed.
"""
import importlib.util
import itertools
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("mmflags_builder", Path(__file__).with_name("build_kernel.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
FIXTURES = Path(__file__).with_name("fixtures")


def patched_header():
    fixture = FIXTURES / "oh66-mmflags.h"
    if builder.sha256(fixture) != "b5e688ad525a978a90136bc94b513d3701b3097268c22f5ec0be31fab081eb41":
        raise ValueError("The pinned mmflags source fixture changed")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "include/trace/events/mmflags.h"
        source.parent.mkdir(parents=True)
        source.write_bytes(fixture.read_bytes())
        prefix = ["git", "-c", "core.autocrlf=false", "-C", str(root)]
        subprocess.run(prefix + ["init", "-q"], check=True, capture_output=True)
        for spec in builder.load_targets()["oh66-ft8716"].get("support_patches", []):
            if spec["path"].endswith("oh66-xpm-mmflags-guard-review.patch"):
                patch = builder.PROJECT / spec["path"]
                if builder.sha256(patch) != spec["sha256"]:
                    raise ValueError("XPM support patch hash mismatch")
                subprocess.run(prefix + ["apply", "--check", str(patch)], check=True, capture_output=True)
                subprocess.run(prefix + ["apply", str(patch)], check=True, capture_output=True)
        return source.read_text(encoding="utf-8")


def definition(source, name):
    match = re.search(r"(#ifdef (CONFIG_[A-Z0-9_]+)\n#define " + re.escape(name)
                      + r"\(_name\)[^\n]+\n#else\n#define " + re.escape(name)
                      + r"\(_name\)\n#endif)", source)
    if not match:
        raise ValueError("Expected a simple conditional macro: " + name)
    return match[1], match[2]


def calls(source):
    table = source.split("#define __def_pageflag_names", 1)[1].split("#define show_page_flags", 1)[0]
    result = re.findall(r"\b(IF_HAVE_PG_[A-Z0-9_]+)\((xpm_readonly|xpm_writetainted)\)", table)
    if len(result) != 2:
        raise ValueError("Expected exactly two XPM table entries")
    return result


class XpmFlagsTests(unittest.TestCase):
    def test_enum_and_table_match_for_all_configurations(self):
        source = patched_header()
        enum = (FIXTURES / "oh66-xpm-pageflags-enum.h").read_text()
        enum_guard = re.search(r"#ifdef (CONFIG_[A-Z0-9_]+)", enum)[1]
        members = re.findall(r"PG_(xpm_\w+),", enum)
        for xpm, arch in itertools.product((False, True), repeat=2):
            with self.subTest(xpm=xpm, arch=arch):
                enabled = {name for name, active in (("CONFIG_SECURITY_XPM", xpm),
                           ("CONFIG_ARCH_USES_PG_ARCH_X", arch)) if active}
                declared = members if enum_guard in enabled else []
                emitted = [name for macro, name in calls(source) if definition(source, macro)[1] in enabled]
                self.assertEqual(emitted, declared,
                                 "mmflags table must use the same guard as the XPM enum, independently of architecture flags")

    def test_minimized_c_matrix_with_host_compiler(self):
        compiler = shutil.which("gcc")
        if not compiler:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("HOST GCC is required for the CI preprocessor regression")
            self.skipTest("No local GCC; actual C matrix runs on Linux CI without local installation")
        source = patched_header()
        enum = (FIXTURES / "oh66-xpm-pageflags-enum.h").read_text()
        definitions = "\n".join(definition(source, name)[0] for name in
                                ("IF_HAVE_PG_ARCH_X", "IF_HAVE_PG_XPM_INTEGRITY"))
        table_calls = "\n".join(f"{macro}({name})" for macro, name in calls(source))
        for xpm, arch in itertools.product((False, True), repeat=2):
            with self.subTest(xpm=xpm, arch=arch):
                config = "".join(f"#define {name} 1\n" for name, active in
                                 (("CONFIG_SECURITY_XPM", xpm), ("CONFIG_ARCH_USES_PG_ARCH_X", arch)) if active)
                harness = (config + "#define __stringify(x) #x\n"
                           + "enum pageflags { PG_base,\n" + enum + "\n__NR_PAGEFLAGS };\n"
                           + definitions + "\nstruct trace_print_flags { unsigned long mask; const char *name; };\n"
                           + "static const struct trace_print_flags names[] = {{1UL << PG_base, \"base\"}\n"
                           + table_calls + "\n};\n"
                           + '_Static_assert(sizeof(names)/sizeof(names[0]) == __NR_PAGEFLAGS, "pageflag table mismatch");\n')
                result = subprocess.run([compiler, "-std=c11", "-Werror", "-fsyntax-only", "-x", "c", "-"],
                                        input=harness, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                if not xpm and arch:
                    original = (FIXTURES / "oh66-mmflags.h").read_text(encoding="utf-8")
                    old_calls = "\n".join(f"{macro}({name})" for macro, name in calls(original))
                    negative = subprocess.run([compiler, "-std=c11", "-Werror", "-fsyntax-only", "-x", "c", "-"],
                                              input=harness.replace(table_calls, old_calls),
                                              capture_output=True, text=True, timeout=15)
                    self.assertNotEqual(negative.returncode, 0, "Original failing source must stay red in the C regression")
                    self.assertIn("PG_xpm_readonly", negative.stderr)


if __name__ == "__main__":
    unittest.main()
