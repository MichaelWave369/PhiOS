#!/usr/bin/env python3
"""Reviewed Vessie offline profile: remove one remote Google Font CSS import.
Generated assets only; no upstream source change and no launch authority.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

FONT_URL = 'https://fonts.googleapis.com/css2?'


def find_import_rules(css: str) -> list[tuple[int, int, str]]:
    """Locate CSS @import statements, preserving semicolons inside quoted URLs."""
    output = []
    for match in re.finditer(r"""@import(?=[\s"'(]|url\()""", css, flags=re.IGNORECASE):
        pos = match.end()
        quote = None
        depth = 0
        while pos < len(css):
            char = css[pos]
            if quote is not None:
                if char == '\\':
                    pos += 2
                    continue
                if char == quote:
                    quote = None
            elif char in ('"', "'"):
                quote = char
            elif char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth < 0:
                    raise ValueError('FONT_IMPORT_UNBALANCED')
            elif char == ';' and depth == 0:
                output.append((match.start(), pos + 1, css[match.start():pos + 1]))
                break
            pos += 1
        else:
            raise ValueError('FONT_IMPORT_UNTERMINATED')
    return output


def strip_fonts(css: str) -> tuple[str, int]:
    """Never silently remove an unreviewed remote CSS import."""
    rules = find_import_rules(css)
    removed = 0
    for start, end, rule in reversed(rules):
        if FONT_URL not in rule:
            if re.search(r'https?://', rule):
                raise ValueError('UNREVIEWED_REMOTE_CSS_IMPORT')
            continue
        if 'DM+Mono' not in rule or 'Space+Grotesk' not in rule:
            raise ValueError('FONT_IMPORT_IDENTITY_DRIFT')
        if removed:
            raise ValueError('MULTIPLE_REMOTE_FONT_IMPORTS')
        css = css[:start] + css[end:]
        removed += 1
    if 'fonts.googleapis.com' in css or 'fonts.gstatic.com' in css:
        raise ValueError('REMOTE_FONT_REFERENCE_REMAINS')
    if re.search(r"""url\(\s*["' ]?https?://""", css, re.IGNORECASE):
        raise ValueError('UNREVIEWED_REMOTE_ASSET')
    return css, removed


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('OFFLINE_ROOT_NOT_DIRECTORY')
    css_files = sorted((root / 'assets').glob('*.css'))
    if not css_files or len(css_files) > 12:
        raise ValueError('OFFLINE_CSS_SET_INVALID')
    changes = []
    found = 0
    pending = []
    for css_path in css_files:
        if css_path.is_symlink() or not css_path.is_file():
            raise ValueError('OFFLINE_CSS_NONREGULAR')
        before = css_path.read_bytes()
        after, count = strip_fonts(before.decode('utf-8'))
        found += count
        if count:
            new = after.encode('utf-8')
            pending.append((css_path, new))
            changes.append({'asset': css_path.relative_to(root).as_posix(),
                            'before_sha256': digest(before), 'after_sha256': digest(new),
                            'removed_google_font_imports': count})
    if found != 1:
        raise ValueError(f'EXPECTED_EXACTLY_ONE_GOOGLE_FONT_IMPORT:{found}')
    for path, content in pending:
        path.write_bytes(content)
    return {'schema': 'phios.offline_font_fallback.v0.1',
            'app': 'vessie-web', 'scope': 'generated compiled CSS only',
            'reviewed_imports_removed': found, 'assets': changes,
            'external_font_bundled': False, 'license_audit_complete': False,
            'phios_install_authorized': False, 'external_done': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = transform(args.output_root)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
