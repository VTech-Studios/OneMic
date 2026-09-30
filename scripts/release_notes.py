from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION_FILE = ROOT / "onemic" / "__init__.py"
_VERSION = re.compile(r'^__version__ = "(?P<version>[^"]+)"$', re.MULTILINE)


class ReleaseError(RuntimeError):
    """The repository is not in a state that can be released."""


def version_from_tag(tag: str) -> str:
    """Strip the conventional v prefix from a tag.

    @param tag: a tag such as v1.0.0.
    @return: the bare version, such as 1.0.0.
    """
    return tag.removeprefix("v")


def package_version(source: str) -> str:
    """Read the version from the package source without importing it.

    Importing would need PySide6 and NumPy, which the release job does not
    install before building.

    @param source: the text of onemic/__init__.py.
    @return: the version string.
    @raise ReleaseError: if no version is declared.
    """
    match = _VERSION.search(source)
    if match is None:
        raise ReleaseError("__version__ not found in onemic/__init__.py")
    return match["version"]


def check_tag(tag: str, source: str) -> None:
    """Refuse a tag that does not match the package version.

    A mistyped tag would otherwise publish files labelled with the wrong version.

    @param tag: the release tag.
    @param source: the text of onemic/__init__.py.
    @raise ReleaseError: if they disagree.
    """
    version = package_version(source)
    if version_from_tag(tag) != version:
        raise ReleaseError(f"Tag {tag} does not match the package version {version}")


def section(changelog: str, version: str) -> str:
    """Take one version's notes from the changelog, for the release page.

    Sections follow Keep a Changelog: a "## [1.0.0] - date" heading, running
    until the next "## " heading or the link references at the end.

    @param changelog: the text of CHANGELOG.md.
    @param version: the version to extract.
    @return: the section's body.
    @raise ReleaseError: if the section is missing or empty.
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n", re.MULTILINE)
    start = heading.search(changelog)
    if start is None:
        raise ReleaseError(f"CHANGELOG.md has no section for {version}")
    end = re.compile(r"^(## |\[[^\]]+\]: )", re.MULTILINE).search(changelog, start.end())
    body = changelog[start.end() : end.start() if end else len(changelog)].strip()
    if not body:
        raise ReleaseError(f"CHANGELOG.md section for {version} is empty")
    return body + "\n"


def main(argv: list[str] | None = None) -> int:
    """Print a version's release notes, or with --check-tag, check the tag.

    @param argv: command line arguments, defaulting to the process's own.
    @return: the exit status, 1 if the repository cannot be released.
    """
    parser = argparse.ArgumentParser(description="Release helpers used by the release workflow.")
    parser.add_argument("tag", help="release tag, for example v1.0.0")
    parser.add_argument("--check-tag", action="store_true", help="only check the tag against the version")
    args = parser.parse_args(argv)
    try:
        if args.check_tag:
            check_tag(args.tag, VERSION_FILE.read_text(encoding="utf-8"))
        else:
            sys.stdout.write(section(CHANGELOG.read_text(encoding="utf-8"), version_from_tag(args.tag)))
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
