from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('os_ci_gate', Path(__file__).parents[1] / 'scripts/os_ci_gate.py')
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def results(image: str = 'true', ui: str = 'true') -> dict:
    return {'changes': {'result': 'success', 'outputs': {'image': image, 'ui': ui}},
            'python-tests': {'result': 'success'},
            'phishell': {'result': 'success' if ui == 'true' else 'skipped'},
            'normal-image': {'result': 'success' if image == 'true' else 'skipped'},
            'qa-image': {'result': 'success' if image == 'true' else 'skipped'}}


@pytest.mark.parametrize('job', ['python-tests', 'phishell', 'normal-image', 'qa-image'])
@pytest.mark.parametrize('result', ['failure', 'cancelled', 'skipped'])
def test_requested_failure_cancellation_or_skip_never_passes(job, result):
    needs = results()
    needs[job]['result'] = result
    with pytest.raises(ValueError):
        gate.verify(needs)


def test_only_explicitly_unrequested_jobs_may_skip():
    assert gate.verify(results('false', 'false'))['normal-image'] == 'skipped'
    assert gate.verify(results('false', 'true'))['phishell'] == 'success'
    assert gate.verify(results())['normal-image'] == 'success'
    needs = results('false', 'false')
    needs['python-tests']['result'] = 'skipped'
    with pytest.raises(ValueError):
        gate.verify(needs)


@pytest.mark.parametrize('scope', [{}, {'image': 'false'}, {'image': True, 'ui': 'true'},
                                  {'image': 'true', 'ui': 'false'}])
def test_missing_or_inconsistent_scope_holds(scope):
    needs = results()
    needs['changes']['outputs'] = scope
    with pytest.raises(ValueError):
        gate.verify(needs)


def test_failed_scope_or_missing_job_holds():
    needs = results('false', 'false')
    needs['changes']['result'] = 'failure'
    with pytest.raises(ValueError):
        gate.verify(needs)
    del needs['qa-image']
    with pytest.raises(ValueError):
        gate.verify(needs)


@pytest.mark.parametrize('path', ['packaging/linux/build-linux.sh', 'phios/__init__.py',
                                 '.github/workflows/ci.yml', 'tests/new.py', 'new-build-input',
                                 'docs/schema.json', 'packaging/README.md', 'docs/../payload.md'])
def test_unknown_or_executable_inputs_require_both_images(path):
    assert gate.plan('pull_request', ['docs/os/RELEASE_HANDOFF.md', path]) == {'image': 'true', 'ui': 'true'}


def test_complete_documentation_scope_and_final_runs():
    paths = ['README.md', 'docs/os/RELEASE_HANDOFF.md', 'docs/os/evidence/receipt.json']
    assert gate.plan('pull_request', paths) == {'image': 'false', 'ui': 'false'}
    assert gate.plan('pull_request', ['docs/PHISHELL_V0.1.md']) == {'image': 'false', 'ui': 'true'}
    for event in ['push', 'workflow_dispatch']:
        assert gate.plan(event, paths) == {'image': 'true', 'ui': 'true'}
    for unobserved in [None, []]:
        assert gate.plan('pull_request', unobserved) == {'image': 'true', 'ui': 'true'}


def test_complete_local_diff_includes_deleted_runtime_after_many_documents(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args], cwd=tmp_path, text=True).strip()

    git('init', '-q')
    runtime = tmp_path / 'phios/runtime.py'
    runtime.parent.mkdir()
    runtime.write_text('runtime\n')
    git('add', '.')
    git('commit', '-qm', 'base')
    base = git('rev-parse', 'HEAD')
    documents = tmp_path / 'docs'
    documents.mkdir()
    for i in range(350):
        (documents / f'{i:03}.md').write_text('document\n')
    runtime.unlink()
    git('add', '.')
    git('commit', '-qm', 'remove runtime after many documents')
    head = git('rev-parse', 'HEAD')
    paths = gate.changed_paths({'pull_request': {'base': {'sha': base}, 'head': {'sha': head}}}, tmp_path)
    assert paths is not None and len(paths) == 351 and 'phios/runtime.py' in paths
    assert gate.plan('pull_request', paths)['image'] == 'true'


def test_unavailable_diff_requires_full_scope(tmp_path):
    paths = gate.changed_paths({'pull_request': {'base': {'sha': 'a' * 40}, 'head': {'sha': 'b' * 40}}}, tmp_path)
    assert paths is None
    assert gate.plan('pull_request', paths)['image'] == 'true'
