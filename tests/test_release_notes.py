import pytest

from scripts.release_notes import (
    CHANGELOG,
    VERSION_FILE,
    ReleaseError,
    check_tag,
    main,
    package_version,
    section,
    version_from_tag,
)

CHANGELOG_TEXT = """# Changelog

## [Unreleased]

## [1.1.0] - 2026-10-01

### Fixed

- Something.

## [1.0.0] - 2026-09-30

First release.

[Unreleased]: https://example.com/compare/v1.1.0...HEAD
[1.1.0]: https://example.com/releases/tag/v1.1.0
"""


def test_version_from_tag() -> None:
    assert version_from_tag("v1.0.0") == "1.0.0"
    assert version_from_tag("1.0.0") == "1.0.0"


def test_package_version() -> None:
    assert package_version('__version__ = "1.2.3"\n') == "1.2.3"
    with pytest.raises(ReleaseError):
        package_version("nothing here")


def test_a_tag_must_match_the_version() -> None:
    check_tag("v1.2.3", '__version__ = "1.2.3"\n')
    with pytest.raises(ReleaseError, match="does not match"):
        check_tag("v1.2.4", '__version__ = "1.2.3"\n')


def test_a_section_runs_to_the_next_heading() -> None:
    assert section(CHANGELOG_TEXT, "1.1.0") == "### Fixed\n\n- Something.\n"


def test_the_last_section_stops_at_the_links() -> None:
    assert section(CHANGELOG_TEXT, "1.0.0") == "First release.\n"


def test_missing_and_empty_sections_are_refused() -> None:
    with pytest.raises(ReleaseError, match="no section"):
        section(CHANGELOG_TEXT, "9.9.9")
    with pytest.raises(ReleaseError, match="empty"):
        section("## [2.0.0] - 2026-10-02\n\n## [1.0.0]\n", "2.0.0")


def test_the_real_repository_is_releasable(capsys: pytest.CaptureFixture[str]) -> None:
    version = package_version(VERSION_FILE.read_text(encoding="utf-8"))

    assert main(["--check-tag", f"v{version}"]) == 0
    assert main([f"v{version}"]) == 0
    assert capsys.readouterr().out.strip()
    assert f"## [{version}]" in CHANGELOG.read_text(encoding="utf-8")


def test_a_bad_tag_fails_with_a_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--check-tag", "v0.0.1"]) == 1
    assert "does not match" in capsys.readouterr().err
