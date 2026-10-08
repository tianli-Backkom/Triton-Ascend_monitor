import unittest
from dashboard import build_batches, build_payload
from quality import validate

class PRQualityTests(unittest.TestCase):
    def run_row(self):
        return {"id":1,"event":"pull_request","head_sha":"sha","created_at":"2026-10-08T00:00:00Z","updated_at":"2026-10-08T00:01:00Z","status":"completed","conclusion":"success","jobs":[],"jobs_complete":True,"pr":23,"pr_title":"Title","pr_url":"https://github.com/triton-lang/triton-ascend/pull/23","base_branch":"main","pr_evidence":{"method":"head","run_id":1,"pr":23,"resolved_head_sha":"sha"}}
    def payload(self,rows):
        return build_payload(rows,"2026-10-05T00:00:00Z","2026-10-08T00:05:00Z","2026-10-08T00:05:00Z")
    def test_missing_pr_blocks_publication(self):
        r=self.run_row();r['pr']=None
        self.assertFalse(validate([r],self.payload([r]))['passed'])
    def test_evidence_from_another_run_blocks_publication(self):
        r=self.run_row();r['pr_evidence']['run_id']=42
        self.assertFalse(validate([r],self.payload([r]))['passed'])
    def test_missing_evidence_blocks_publication(self):
        r=self.run_row();r['pr_evidence']=None
        self.assertFalse(validate([r],self.payload([r]))['passed'])
    def test_lost_batch_identity_blocks_publication(self):
        r=self.run_row();p=self.payload([r]);p['batches'][0]['pr']=999
        self.assertFalse(validate([r],p)['passed'])
    def test_valid_metadata_passes(self):
        r=self.run_row();self.assertTrue(validate([r],self.payload([r]))['passed'])
    def test_unknown_runs_do_not_merge_on_shared_sha(self):
        r=self.run_row();r['pr']=None
        self.assertEqual(len(build_batches([r,{**r,'id':2}],"2026-10-08T00:05:00Z")),2)
