"""Read-only GenomeMemory fixture review. No registry, memory or authority writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'genomememory-living-demo/v1'
FIELDS = {'schema','synthetic','authority','experimental_pass','live_ready','checks',
          'blockers','evidence_sha256'}
CHECKS = {'source_creation','native_export','representation','integrity','consent',
          'packet_review','learning','revocation','restart'}


def review(report):
    """Validate declared results, while withholding all integration authority.

    The report and evidence digest are untrusted declarations. A structurally
    correct report is not an execution attestation or an authorization.
    """
    if type(report) is not dict or set(report) != FIELDS:
        raise ValueError('invalid GenomeMemory advisory report fields')
    if (report['schema'] != SCHEMA or report['synthetic'] is not True or
            report['authority'] != 'NONE' or report['live_ready'] is not False or
            type(report['experimental_pass']) is not bool):
        raise ValueError('unsupported contract or claimed production authority')
    checks = report['checks']
    if type(checks) is not dict or set(checks) != CHECKS or any(type(v) is not bool for v in checks.values()):
        raise ValueError('nine explicit boolean checks required')
    if report['experimental_pass'] != all(checks.values()):
        raise ValueError('inconsistent declared experiment status')
    blockers = report['blockers']
    if (type(blockers) is not list or not 1 <= len(blockers) <= 32 or
            any(type(v) is not str or not re.fullmatch(r'[a-z0-9_]{1,96}',v) for v in blockers) or
            len(set(blockers)) != len(blockers)):
        raise ValueError('explicit unresolved integration blockers required')
    digest = report['evidence_sha256']
    if type(digest) is not str or not re.fullmatch(r'[0-9a-f]{64}',digest):
        raise ValueError('invalid declared evidence commitment')
    raw = json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
    return dict(schema='phios-genomememory-advisory/v1',status='HELD',authority='NONE',
                declared_experimental_pass=report['experimental_pass'],evidence_verified=False,
                report_sha256=hashlib.sha256(raw).hexdigest(),blockers=list(blockers),
                reason='untrusted_fixture_declarations_require_independent_review')


def load_report(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('bounded regular report file required')
    def unique(pairs):
        out = {}
        for key,value in pairs:
            if key in out: raise ValueError('duplicate JSON key')
            out[key] = value
        return out
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    try:
        result=review(load_report(args.report))
    except (OSError,ValueError,TypeError) as exc:
        print(json.dumps(dict(status='INVALID',authority='NONE',reason=str(exc))))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 3  # HELD is intentional, including when every declared check passes.


if __name__ == '__main__':
    raise SystemExit(main())

