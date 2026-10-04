"""Always-reported CI aggregation; a passing result is not release authority."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

JOBS = ('changes', 'python-tests', 'phishell', 'normal-image', 'qa-image')
SHA = re.compile(r'[0-9a-f]{40}')


def documentation(path: str) -> bool:
    parts = path.split('/')
    if any(part in ('', '.', '..') for part in parts) or '\\' in path:
        return False
    if len(parts) == 1:
        return path.endswith('.md')
    if parts[0] == 'docs' and path.endswith('.md'):
        return True
    return path.startswith('docs/os/evidence/') and path.endswith('.json')


def plan(event_name: str, paths: list[str] | None) -> dict[str, str]:
    # Every final main push, OS tag and manual run exercises both exact images.
    # Only an observed documentation-only PR can omit their expensive jobs.
    image = event_name != 'pull_request' or not paths or any(not documentation(p) for p in paths)
    ui = image or any(p.startswith('docs/PHISHELL_') for p in paths or [])
    return {'image': str(image).lower(), 'ui': str(ui).lower()}


def changed_paths(event: dict[str, Any], root: Path) -> list[str] | None:
    request = event.get('pull_request')
    if not isinstance(request, dict):
        raise ValueError('missing pull-request context')
    base = request.get('base', {}).get('sha')
    head = request.get('head', {}).get('sha')
    if not isinstance(base, str) or not isinstance(head, str) or not SHA.fullmatch(base) or not SHA.fullmatch(head):
        raise ValueError('invalid diff identities')
    try:
        # Two complete trees include deletions and changes introduced by a moved
        # base. No API pagination/300-file path filter or rename omission applies.
        data = subprocess.check_output(
            ['git', 'diff', '--no-ext-diff', '--no-renames', '--name-only', '-z', base, head, '--'],
            cwd=root,
        )
        if data and not data.endswith(b'\0'):
            raise ValueError('incomplete changed-path output')
        return [p.decode('utf-8') for p in data.split(b'\0') if p]
    except (subprocess.CalledProcessError, UnicodeDecodeError):
        # An unavailable/unreadable diff requires full image qualification.
        return None


def verify(needs: dict[str, Any]) -> dict[str, str]:
    if set(needs) != set(JOBS) or any(not isinstance(needs[k], dict) for k in JOBS):
        raise ValueError('incomplete required job results')
    if needs['changes'].get('result') != 'success':
        raise ValueError('qualification scope did not succeed')
    scope = needs['changes'].get('outputs')
    if not isinstance(scope, dict) or set(scope) != {'image', 'ui'} or any(v not in ('true', 'false') for v in scope.values()):
        raise ValueError('invalid qualification scope outputs')
    if scope['image'] == 'true' and scope['ui'] != 'true':
        raise ValueError('image qualification requires UI qualification')
    expected = {'changes': 'success', 'python-tests': 'success',
                'phishell': 'success' if scope['ui'] == 'true' else 'skipped',
                'normal-image': 'success' if scope['image'] == 'true' else 'skipped',
                'qa-image': 'success' if scope['image'] == 'true' else 'skipped'}
    for job, result in expected.items():
        if needs[job].get('result') != result:
            raise ValueError(f'required qualification result held: {job}')
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'check'))
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            event_name = os.environ['GITHUB_EVENT_NAME']
            paths = None
            if event_name == 'pull_request':
                event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
                paths = changed_paths(event, Path.cwd())
            scope = plan(event_name, paths)
            with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
                for key, value in scope.items():
                    stream.write(f'{key}={value}\n')
            print(json.dumps({'required': scope, 'complete_diff_observed': paths is not None}, sort_keys=True))
        else:
            results = verify(json.loads(os.environ['PHIOS_CI_NEEDS']))
            print(json.dumps({'schema_version': 'phios.ci-qualification.v1',
                'source_commit': os.environ['GITHUB_SHA'], 'job_results': results,
                'release_ready': False, 'publication_authority': False}, sort_keys=True))
        return 0
    except (KeyError, OSError, ValueError, TypeError, AttributeError) as exc:
        print(f'::error::PhiOS qualification held: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
