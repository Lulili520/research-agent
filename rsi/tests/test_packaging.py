"""检查文档链接、角色能力入口与运行时依赖边界。"""
import ast
from pathlib import Path
import re
import sys
import unittest

from rsi.runtime.contracts import SKILLS

ROOT = Path(__file__).resolve().parents[2]


class PackagingTests(unittest.TestCase):
    def test_role_skills_exist(self):
        for names in SKILLS.values():
            for name in names:
                self.assertTrue((ROOT / "rsi/skills" / name / "SKILL.md").is_file())

    def test_local_markdown_links_resolve(self):
        paths = [ROOT / "AGENTS.md", ROOT / "README.md", *(ROOT / "rsi").rglob("*.md")]
        for path in paths:
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                target = target.split("#", 1)[0]
                self.assertTrue((path.parent / target).is_file(), f"{path}: broken link {target}")

    def test_runtime_dependencies_are_standard_library_or_local(self):
        paths = [ROOT / "rsi/__init__.py", ROOT / "rsi/__main__.py",
                 *(ROOT / "rsi/runtime").rglob("*.py")]
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    imports = [node.module or ""]
                else:
                    continue
                for name in imports:
                    package = name.split(".", 1)[0]
                    self.assertTrue(package == "rsi" or package in sys.stdlib_module_names,
                                    f"{path}:{node.lineno}: unsupported runtime dependency {name}")


if __name__ == "__main__":
    unittest.main()
