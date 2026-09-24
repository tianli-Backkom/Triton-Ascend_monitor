import unittest
from datetime import datetime, timezone

from dashboard import (
    build_batches,
    extract_focus_job_links,
    extract_pr_base_ref,
    merge_run_evidence,
    parse_job_header,
    parse_pr_base_html,
    parse_run_html,
    percentile,
)


def run(run_id, name, sha, created, updated, status="completed", conclusion="success", attempt=1, jobs=None):
    return {
        "id": run_id,
        "name": name,
        "head_sha": sha,
        "created_at": created,
        "updated_at": updated,
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "html_url": f"https://github.com/example/actions/runs/{run_id}",
        "jobs": jobs or [],
        "pr": 42,
        "pr_title": "Improve compiler",
        "pr_url": "https://github.com/example/pull/42",
        "trigger_at": "2026-09-22T00:00:00Z",
        "trigger_exact": True,
    }


class BatchAggregationTests(unittest.TestCase):
    def test_parallel_workflows_use_last_completion_not_sum(self):
        rows = [
            run(1, "Fast", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:11:00Z"),
            run(2, "Slow", "abc", "2026-09-22T00:02:00Z", "2026-09-22T00:31:00Z"),
        ]
        batch = build_batches(rows, "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["duration_seconds"], 31 * 60)
        self.assertEqual(batch["critical_workflow"], "Slow")

    def test_batch_exposes_focus_jobs_for_chart_cards(self):
        row = run(1, "Integration Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:11:00Z")
        row["focus_jobs"] = [{"key":"a3-py310","name":"A3 py3.10","url":"https://github.com/job/1","wait_seconds":25,"run_seconds":838}]
        batch = build_batches([row], "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["focus_jobs"][0]["key"], "a3-py310")
        self.assertEqual(batch["focus_jobs"][0]["wait_seconds"], 25)

    def test_running_batch_reports_elapsed_and_is_not_complete(self):
        rows = [run(1, "NPU", "abc", "2026-09-22T23:00:00Z", "2026-09-22T23:30:00Z", status="in_progress", conclusion=None)]
        batch = build_batches(rows, "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["status"], "running")
        self.assertEqual(batch["duration_seconds"], 24 * 60 * 60)
        self.assertFalse(batch["complete"])

    def test_failure_wins_over_success_for_completed_batch(self):
        rows = [
            run(1, "Lint", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:05:00Z"),
            run(2, "Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:06:00Z", conclusion="failure"),
        ]
        self.assertEqual(build_batches(rows, "2026-09-23T00:00:00Z")[0]["status"], "failure")

    def test_rerun_is_kept_as_separate_batch(self):
        rows = [
            run(1, "Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:06:00Z"),
            run(1, "Tests", "abc", "2026-09-22T01:01:00Z", "2026-09-22T01:08:00Z", attempt=2),
        ]
        batches = build_batches(rows, "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 2)
        self.assertEqual({b["kind"] for b in batches}, {"initial", "rerun"})

    def test_same_pr_and_sha_are_one_initial_e2e_even_when_workflows_arrive_late(self):
        first = run(1, "Title", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:02:00Z")
        second = run(2, "Title", "abc", "2026-09-22T03:01:00Z", "2026-09-22T03:02:00Z")
        second["trigger_at"] = "2026-09-22T03:00:00Z"
        batches = build_batches([first, second], "2026-09-23T00:00:00Z")
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]["workflows"]), 2)

    def test_batch_exposes_actual_action_run_links(self):
        rows = [
            run(1, "Documentation", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:05:00Z"),
            run(2, "Integration Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:08:00Z"),
        ]
        batch = build_batches(rows, "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["action_url"], "https://github.com/example/actions/runs/2")
        self.assertEqual(batch["action_name"], "Integration Tests")

    def test_batch_uses_longest_npu_job_queue_time(self):
        jobs = [
            {"id": 11, "name": "runner-preparation / prepare", "created_at": "2026-09-22T00:01:00Z", "started_at": "2026-09-22T00:01:03Z", "completed_at": "2026-09-22T00:01:05Z", "html_url": "https://github.com/job/11", "status": "completed", "conclusion": "success"},
            {"id": 12, "name": "integration-tests-ascend (linux-aarch64-a3-800i-4, py3.10)", "created_at": "2026-09-22T00:01:05Z", "started_at": "2026-09-22T00:01:45Z", "completed_at": "2026-09-22T00:06:00Z", "html_url": "https://github.com/job/12", "status": "completed", "conclusion": "success"},
            {"id": 13, "name": "integration-tests-ascend (linux-aarch64-a3-800i-4, py3.11)", "created_at": "2026-09-22T00:01:05Z", "started_at": "2026-09-22T00:02:15Z", "completed_at": "2026-09-22T00:07:00Z", "html_url": "https://github.com/job/13", "status": "completed", "conclusion": "success"},
        ]
        batch = build_batches([run(2, "Integration Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:08:00Z", jobs=jobs)], "2026-09-23T00:00:00Z")[0]
        self.assertEqual(batch["npu_queue_seconds"], 70)
        self.assertEqual([job["id"] for job in batch["npu_jobs"]], [12, 13])

    def test_approximate_start_is_retained_and_marked(self):
        row = run(1, "Tests", "abc", "2026-09-22T00:01:00Z", "2026-09-22T00:06:00Z")
        row["trigger_at"] = None
        row["trigger_exact"] = False
        batch = build_batches([row], "2026-09-23T00:00:00Z")[0]
        self.assertTrue(batch["approximate"])
        self.assertEqual(batch["start_at"], "2026-09-22T00:01:00Z")
        self.assertNotIn("提交事件", " ".join(batch["missing"]))


class PercentileTests(unittest.TestCase):
    def test_percentile_uses_linear_interpolation(self):
        self.assertEqual(percentile([10, 20, 30, 40], 0.9), 37)

    def test_empty_percentile_is_none(self):
        self.assertIsNone(percentile([], 0.9))


class HtmlEvidenceTests(unittest.TestCase):
    def test_pr_api_payload_extracts_merge_target_branch(self):
        self.assertEqual(extract_pr_base_ref({"base": {"ref": "release/3.3"}}), "release/3.3")
        self.assertIsNone(extract_pr_base_ref({}))

    def test_pr_page_parser_extracts_merge_target_branch(self):
        source = '<script type="application/json">{"pullRequest":{"baseBranch":"release/3.2.2","headBranch":"feature"}}</script>'
        self.assertEqual(parse_pr_base_html(source), "release/3.2.2")

    def test_run_page_parser_extracts_pr_status_and_jobs(self):
        source = '''
        <span class="PageHeader-parentLink-label"> Integration Tests</span>
        <svg aria-label="completed with failures: "></svg>
        <h1><span class="markdown-title">Fix compiler</span></h1>
        <a href="/triton-lang/triton-ascend/pull/42">#42</a>
        <relative-time datetime="2026-09-22T01:02:03Z"></relative-time>
        <streaming-graph-job><span data-target="streaming-graph-job.name">Build &amp; Test</span>
        <div class="flex-self-baseline text-small color-fg-muted flex-shrink-0 pl-1"> 2m 5s </div></streaming-graph-job>
        '''
        row = parse_run_html(source)
        self.assertEqual(row["name"], "Integration Tests")
        self.assertEqual(row["pr"], 42)
        self.assertEqual(row["conclusion"], "failure")
        self.assertEqual(row["created_at"], "2026-09-22T01:02:03Z")
        self.assertEqual(row["jobs"][0]["name"], "Build & Test")
        self.assertEqual(row["jobs"][0]["duration_seconds"], 125)

    def test_api_terminal_state_wins_when_html_label_is_ambiguous(self):
        api = {"id": 7, "name": "Label", "status": "completed", "conclusion": "skipped"}
        page = {"name": "Label", "status": "in_progress", "conclusion": None, "jobs": [], "pr": 42}
        merged = merge_run_evidence(api, page)
        self.assertEqual(merged["status"], "completed")
        self.assertEqual(merged["conclusion"], "skipped")

    def test_extracts_only_requested_matrix_jobs_with_direct_links(self):
        source = '''
        <a href="/triton-lang/triton-ascend/actions/runs/9/job/101#step:2:1"><strong>
        integration-tests-ascend / integration-tests-ascend (linux-aarch64-a3-800i-4, py3.10)
        </strong></a>
        <a href="/triton-lang/triton-ascend/actions/runs/9/job/102"><strong>
        integration-tests-ascend / integration-tests-ascend (linux-amd64-cpu-16, py3.11)
        </strong></a>
        '''
        jobs = extract_focus_job_links(source)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], 101)
        self.assertEqual(jobs[0]["key"], "a3-py310")
        self.assertEqual(jobs[0]["url"], "https://github.com/triton-lang/triton-ascend/actions/runs/9/job/101")

    def test_job_header_derives_queue_and_execution_duration(self):
        source = '''<span>succeeded <relative-time datetime="2026-09-20T08:23:30Z"></relative-time> in 13m 58s</span>'''
        job = parse_job_header(source, "2026-09-20T08:09:07Z", "2026-09-20T09:00:00Z")
        self.assertEqual(job["run_seconds"], 838)
        self.assertEqual(job["wait_seconds"], 25)
        self.assertEqual(job["status"], "completed")


if __name__ == "__main__":
    unittest.main()
