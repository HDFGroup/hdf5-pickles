#!/usr/bin/env python3
"""Check that local destinations in tracked Markdown files exist.

External URLs are deliberately not fetched: this is the deterministic
repository-relative half of link validation and is safe to run offline.
"""

from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\((?:<(?P<angle>[^>\n]+)>|(?P<plain>[^\s)\n]+))"
)
REFERENCE_LINK = re.compile(
    r"^\s{0,3}\[[^\]\n]+\]:\s*(?:<(?P<angle>[^>\n]+)>|(?P<plain>\S+))",
    re.MULTILINE,
)


def tracked_markdown():
    raw = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=ROOT
    )
    return [ROOT / name.decode() for name in raw.split(b"\0") if name]


def is_external(destination):
    if destination.startswith("//"):
        return True
    return bool(urlsplit(destination).scheme)


def local_target(source, destination):
    path_text = unquote(destination.split("#", 1)[0].split("?", 1)[0])
    if not path_text:
        return source
    path = Path(path_text)
    if path.is_absolute():
        return None
    return source.parent / path


def markdown_anchors(text):
    """Return GitHub-style heading slugs plus explicit HTML anchors."""
    anchors = set(
        re.findall(r'<a\s+(?:name|id)=["\']([^"\']+)', text, re.IGNORECASE)
    )
    occurrences = {}
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        heading = re.sub(r"<[^>]*>", "", match.group(1))
        heading = re.sub(r"[`*_~]", "", heading).lower()
        slug = re.sub(r"[^\w\- ]", "", heading)
        slug = re.sub(r"\s+", "-", slug.strip())
        duplicate = occurrences.get(slug, 0)
        occurrences[slug] = duplicate + 1
        anchors.add(slug if duplicate == 0 else f"{slug}-{duplicate}")
    return anchors


def main():
    files = tracked_markdown()
    texts = {source: source.read_text(encoding="utf-8") for source in files}
    anchors = {source.resolve(): markdown_anchors(text)
               for source, text in texts.items()}
    failures = []
    local_links = 0
    for source in files:
        text = texts[source]
        matches = list(INLINE_LINK.finditer(text))
        matches.extend(REFERENCE_LINK.finditer(text))
        for match in matches:
            destination = match.group("angle") or match.group("plain")
            if is_external(destination):
                continue
            target = local_target(source, destination)
            if target is None:
                continue
            local_links += 1
            if not target.exists():
                line = text.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{source.relative_to(ROOT)}:{line}: missing local link "
                    f"target {destination!r}"
                )
                continue
            if "#" in destination and target.suffix.lower() == ".md":
                anchor = unquote(destination.split("#", 1)[1]).lower()
                if anchor and anchor not in anchors.get(target.resolve(), set()):
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line}: missing Markdown "
                        f"anchor {anchor!r} in {target.relative_to(ROOT)!s}"
                    )

    if failures:
        print("\n".join(failures))
        return 1
    print(
        f"MARKDOWN LINK CHECK OK: {local_links} local links across "
        f"{len(files)} tracked Markdown files"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
