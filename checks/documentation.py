"""Check the repository's relative Markdown links and heading anchors offline."""

import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


def prose(text):
    return re.sub(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[^\n]*$", "", text)


def anchors(text):
    seen = {}
    result = set()
    for heading in re.findall(r"(?m)^#{1,6} +(.+?) *#* *$", prose(text)):
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


def check(root):
    root = root.resolve()
    errors = []
    for document in sorted(root.rglob("*.md")):
        if ".git" in document.relative_to(root).parts:
            continue
        text = prose(document.read_text())
        for match in re.finditer(r"\[[^\]\n]*\]\(([^\s)]+)\)", text):
            link = match[1]
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (document.parent / unquote(url.path)).resolve() if url.path else document
            problem = None
            if not target.is_relative_to(root):
                problem = "leaves the repository"
            elif not target.exists():
                problem = "missing target"
            elif url.fragment and target.suffix == ".md":
                if unquote(url.fragment) not in anchors(target.read_text()):
                    problem = "missing heading"
            if problem:
                errors.append(f"{document.relative_to(root)}: {link}: {problem}")
    return errors


class DocumentationTests(unittest.TestCase):
    def test_relative_paths_anchors_and_duplicate_headings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs/guide.md").write_text("# Some `Heading`\n## Repeat\n## Repeat\n")
            readme = root / "README.md"
            readme.write_text(
                "[guide](docs/guide.md#some-heading)\n"
                "[again](docs/guide.md#repeat-1)\n"
                "[external](https://example.invalid/missing)\n"
                "```md\n[example](missing.md)\n```\n"
            )
            self.assertEqual(check(root), [])
            readme.write_text(
                "[file](missing.md)\n[heading](docs/guide.md#absent)\n[private](../outside.md)\n"
            )
            failures = check(root)
            self.assertEqual(len(failures), 3)
            for problem in ("missing target", "missing heading", "leaves the repository"):
                self.assertTrue(any(problem in failure for failure in failures))


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        unittest.main(argv=[sys.argv[0]])
    else:
        failures = check(Path(sys.argv[1]))
        if failures:
            print("\n".join(failures), file=sys.stderr)
            raise SystemExit(1)
        print("Relative Markdown links and heading anchors passed.")
