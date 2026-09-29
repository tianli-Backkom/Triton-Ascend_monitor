import copy,json,unittest
from unittest.mock import patch
from dashboard import GitHub,build_payload
from quality import validate,fingerprint,verify_page

class QualityTests(unittest.TestCase):
    def fixture(self):
        job={"id":7,"name":"integration-tests-ascend (linux-amd64-a5-2, py3.12)","status":"completed","conclusion":"success","created_at":"2026-09-28T01:00:00Z","started_at":"2026-09-28T01:00:14Z","completed_at":"2026-09-28T02:00:00Z"}
        run={"id":1,"pr":1,"head_sha":"abc","created_at":"2026-09-28T01:00:00Z","updated_at":"2026-09-28T02:00:00Z","status":"completed","conclusion":"success","jobs_complete":True,"jobs":[job]}
        runs=[run];p=build_payload(runs,"2026-09-27T00:00:00Z","2026-09-29T00:00:00Z","2026-09-29T00:00:00Z")
        return runs,p
    def test_valid(self):
        r,p=self.fixture();self.assertTrue(validate(r,p)['passed'])
    def test_zero_npu_is_valid(self):
        self.assertTrue(validate([],{'batches':[]})['passed'])
    def test_missing_timestamp(self):
        r,p=self.fixture();r[0]['jobs'][0]['created_at']=None
        self.assertFalse(validate(r,p)['passed'])
    def test_negative_timestamp(self):
        r,p=self.fixture();r[0]['jobs'][0]['started_at']='2026-09-28T00:00:00Z'
        p=build_payload(r,'2026-09-27T00:00:00Z','2026-09-29T00:00:00Z','2026-09-29T00:00:00Z')
        report=validate(r,p)
        self.assertTrue(report['passed'])
        self.assertTrue(report['warnings'])
        self.assertIsNone(p['batches'][0]['npu_queue_seconds'])
    def test_runner_rename(self):
        r,p=self.fixture();r[0]['jobs'][0]['name']='integration-tests-ascend (new-950, py3.12)'
        self.assertFalse(validate(r,p)['passed'])
    def test_lost_aggregation(self):
        r,p=self.fixture();p['batches'][0]['npu_jobs']=[]
        self.assertFalse(validate(r,p)['passed'])
    def test_wrong_maximum(self):
        r,p=self.fixture();p['batches'][0]['npu_queue_seconds']=0
        self.assertFalse(validate(r,p)['passed'])
    def test_pending_is_not_failed_measurement(self):
        r,p=self.fixture();j=r[0]['jobs'][0];j.update(status='queued',conclusion=None,started_at=None,completed_at=None)
        p=build_payload(r,'2026-09-27T00:00:00Z','2026-09-29T00:00:00Z','2026-09-29T00:00:00Z')
        self.assertTrue(validate(r,p)['passed'])
    def test_truncated_page(self):
        with patch.object(GitHub,'get',return_value=({'total_count':5,'jobs':[{'id':1}]},{})):
            with self.assertRaises(RuntimeError):GitHub().pages('/jobs','jobs')
    def test_published_old_data(self):
        r,p=self.fixture();manifest={'sha256':fingerprint(p)}
        html='<script id="data">'+json.dumps(p)+'</script>'
        self.assertEqual(verify_page(html,manifest),p)
        p['collected_at']='old'
        with self.assertRaises(ValueError):verify_page('<script id="data">'+json.dumps(p)+'</script>',manifest)
