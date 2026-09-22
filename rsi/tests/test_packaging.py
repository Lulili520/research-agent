"""只检查可维护性与独立性，不把格式校验称为科学验收。"""
import ast
from pathlib import Path
import re
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

    def test_new_runtime_has_no_old_imports(self):
        for path in (ROOT / "rsi").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(name == "agent" or name.startswith("agent.") for name in imports))


if __name__ == "__main__":
    unittest.main()
