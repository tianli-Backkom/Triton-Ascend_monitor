import unittest
from unittest.mock import patch
from dashboard import GitHub, _job, focus_from_jobs, build_batches

class NpuApiTests(unittest.TestCase):
    def test_missing_created_is_not_zero(self):
        self.assertIsNone(_job({"started_at":"2026-09-28T01:23:45Z"})["wait_seconds"])

    def test_new_a5_and_old_a5_are_recognized(self):
        for runner in ["linux-amd64-a5-2","linux-aarch64-a5-800i-4"]:
            jobs=focus_from_jobs([{"name":f"integration-tests-ascend ({runner}, py3.12)","html_url":"https://github.com/job/1"}])
            self.assertEqual(jobs[0]["key"],"a5-py312")
            self.assertEqual(jobs[0]["url"],"https://github.com/job/1")

    def test_jobs_pagination(self):
        api=GitHub()
        with patch.object(api,"get",side_effect=[({"jobs":[{}]*100},{}),({"jobs":[{}]*3},{})]) as get:
            self.assertEqual(len(api.pages("/actions/runs/1/attempts/1/jobs","jobs")),103)
            self.assertIn("page=2",get.call_args[0][0])

    def test_real_sample(self):
        job={"name":"integration-tests-ascend (linux-aarch64-a3-800i-4, py3.10)","created_at":"2026-09-28T01:23:02Z","started_at":"2026-09-28T01:23:45Z","completed_at":"2026-09-28T01:48:51Z"}
        self.assertEqual(_job(job)["wait_seconds"],43)
        self.assertEqual(_job(job)["run_seconds"],1506)
