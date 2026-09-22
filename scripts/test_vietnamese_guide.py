import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "guide"
VI = GUIDE / "vi"
FILES = (
    "README.md",
    "01-architecture.md",
    "02-cloud-domain.md",
    "03-workstation.md",
    "04-private-resources.md",
    "05-cloudflare-content.md",
    "06-build-android-client.md",
    "07-build-release-content-bundle.md",
    "08-lessons-and-failures.md",
    "09-add-fan-chart.md",
)


def code_blocks(text: str) -> list[str]:
    return re.findall(r"```[^\n]*\n.*?```", text, re.DOTALL)


class VietnameseGuideTests(unittest.TestCase):
    def test_every_guide_chapter_has_a_vietnamese_version(self):
        for name in FILES:
            self.assertTrue((VI / name).is_file(), name)

    def test_commands_are_identical_in_both_languages(self):
        for name in FILES:
            english = (GUIDE / name).read_text(encoding="utf-8")
            vietnamese = (VI / name).read_text(encoding="utf-8")
            self.assertEqual(code_blocks(vietnamese), code_blocks(english), name)

    def test_language_links_and_vietnamese_chapter_links(self):
        root = (ROOT / "README.vi.md").read_text(encoding="utf-8")
        self.assertIn("[English](README.md) | Tiếng Việt", root)
        for name in FILES[1:]:
            self.assertIn(f"docs/guide/vi/{name}", root)
        for name in FILES:
            text = (VI / name).read_text(encoding="utf-8")
            self.assertIn("[English](../", text, name)

    def test_local_markdown_links_resolve(self):
        files = list(GUIDE.rglob("*.md")) + [ROOT / "README.md", ROOT / "README.vi.md"]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                local = target.split("#", 1)[0]
                if local:
                    self.assertTrue((path.parent / local).resolve().exists(), f"{path}: {target}")


if __name__ == "__main__":
    unittest.main()
