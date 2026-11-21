import unittest

from scripts.changelog_notes import extract_section
from scripts.release import ReleaseError, parse_version, replace_version_text, repo_slug_from_url

CHANGELOG = """# Changelog

## [Unreleased]
- 开发中

## [3.1.0] - 2026-12-01

### Added
- 新功能

## [3.0.0] - 2026-11-21

### Fixed
- 旧问题

[Unreleased]: https://example.com/compare
[3.1.0]: https://example.com/3.1.0
"""


class ChangelogExtractionTests(unittest.TestCase):
    def test_extract_version_section(self):
        section = extract_section(CHANGELOG, "3.1.0")
        self.assertIn("### Added", section)
        self.assertIn("新功能", section)
        self.assertNotIn("旧问题", section)

    def test_missing_version(self):
        self.assertIsNone(extract_section(CHANGELOG, "9.9.9"))

    def test_empty_section(self):
        text = "## [9.9.9]\n\n## [3.0.0]\n- x\n"
        self.assertIsNone(extract_section(text, "9.9.9"))


class ReleaseVersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("3.1.0"), (3, 1, 0))
        self.assertEqual(parse_version("v10.0.2"), (10, 0, 2))

    def test_parse_invalid(self):
        with self.assertRaises(ReleaseError):
            parse_version("3.1")
        with self.assertRaises(ReleaseError):
            parse_version("abc")

    def test_replace_version_text(self):
        text = 'APP_VERSION = "3.0.0"\n__version__ = APP_VERSION\n'
        updated = replace_version_text(text, "3.1.0")
        self.assertIn('APP_VERSION = "3.1.0"', updated)
        self.assertNotIn('"3.0.0"', updated)

    def test_replace_requires_app_version(self):
        with self.assertRaises(ReleaseError):
            replace_version_text('VERSION = "3.0.0"\n', "3.1.0")


class RepoSlugTests(unittest.TestCase):
    def test_ssh_url(self):
        self.assertEqual(
            repo_slug_from_url("ssh://git@ssh.github.com:443/MakerYoung/Type2Speech3.git"),
            "MakerYoung/Type2Speech3",
        )
        self.assertEqual(
            repo_slug_from_url("git@github.com:MakerYoung/Type2Speech3.git"),
            "MakerYoung/Type2Speech3",
        )

    def test_https_url(self):
        self.assertEqual(
            repo_slug_from_url("https://github.com/MakerYoung/Type2Speech3.git"),
            "MakerYoung/Type2Speech3",
        )


if __name__ == "__main__":
    unittest.main()
