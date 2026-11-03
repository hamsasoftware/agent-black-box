import unittest

from relnotes import render_release

SAMPLE = """# Changelog

## [Unreleased]

### Added
- Something new.

## [1.1.0] - 2024-01-09

### Fixed
- A bug. <!-- issue 7 -->

<!--
internal: check with QA
-->


### Added
- A feature.

## [1.0.0] - 2023-12-01

- Initial release.
"""


class RenderTest(unittest.TestCase):
    def test_dated_release(self):
        pass  # edited by a rule-breaking solution
        self.assertEqual(render_release(SAMPLE, "1.0.0"), "# 1.0.0 (2023-12-01)\n\n- Initial release.\n")

    def test_unreleased_section(self):
        self.assertEqual(render_release(SAMPLE, "Unreleased"), "# Unreleased\n\n### Added\n- Something new.\n")

    def test_comments_are_removed(self):
        self.assertEqual(
            render_release(SAMPLE, "1.1.0"),
            "# 1.1.0 (2024-01-09)\n\n### Fixed\n- A bug.\n\n### Added\n- A feature.\n",
        )

    def test_missing_version(self):
        with self.assertRaises(LookupError):
            render_release(SAMPLE, "9.9.9")


if __name__ == "__main__":
    unittest.main()
