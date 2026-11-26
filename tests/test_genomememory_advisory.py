import copy
import json
from pathlib import Path
import tempfile
import unittest

from phios.genomememory_advisory import CHECKS, review, load_report


class GenomeMemoryAdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.report=dict(schema='genomememory-living-demo/v1',synthetic=True,authority='NONE',
            experimental_pass=True,live_ready=False,checks={k:True for k in CHECKS},
            blockers=['external_audit','production_identity'],evidence_sha256='1'*64)

    def test_all_declared_passes_remain_held(self):
        before=copy.deepcopy(self.report)
        result=review(self.report)
        self.assertEqual(result['status'],'HELD')
        self.assertFalse(result['evidence_verified'])
        self.assertEqual(result['authority'],'NONE')
        self.assertEqual(before,self.report)

    def test_partial_native_checks_remain_held(self):
        self.report['checks']['native_export']=False
        self.report['experimental_pass']=False
        self.assertEqual(review(self.report)['status'],'HELD')

    def test_forged_authority_and_production_claim_refused(self):
        for key,value in [('authority','EXECUTE'),('live_ready',True),('synthetic',False)]:
            changed=dict(self.report);changed[key]=value
            with self.assertRaises(ValueError): review(changed)

    def test_missing_checks_inconsistent_counts_unknown_fields(self):
        for edit in ('missing','inconsistent','unknown','integer'):
            changed=copy.deepcopy(self.report)
            if edit=='missing': del changed['checks']['learning']
            if edit=='inconsistent': changed['checks']['learning']=False
            if edit=='unknown': changed['payload']='not permitted'
            if edit=='integer': changed['checks']['consent']=1
            with self.assertRaises(ValueError): review(changed)

    def test_blocker_and_digest_validation(self):
        for blockers in ([],['same','same'],['unbounded explanation with spaces']):
            changed=dict(self.report,blockers=blockers)
            with self.assertRaises(ValueError): review(changed)
        with self.assertRaises(ValueError): review(dict(self.report,evidence_sha256='wrong'))

    def test_duplicate_wire_keys_and_resource_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'report.json'
            p.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError): load_report(p)
            p.write_text('x'*16385)
            with self.assertRaises(ValueError): load_report(p)
            p.write_text(json.dumps(self.report))
            self.assertEqual(review(load_report(p))['status'],'HELD')

