"""Regression coverage for fork PR identity and fail-closed association."""
import copy
import json
from pathlib import Path
import re
import unittest
import tempfile
from urllib.parse import parse_qs, urlsplit

from pr_identity import PRResolver


REPO = {"id": 101, "name": "triton-ascend", "full_name": "triton-lang/triton-ascend",
        "owner": {"login": "triton-lang"}}
FORK = {"id": 202, "name": "triton-ascend", "full_name": "contributor/triton-ascend",
        "owner": {"login": "contributor"}}
OTHER_FORK = {"id": 303, "name": "triton-ascend", "full_name": "other/triton-ascend",
              "owner": {"login": "other"}}


def action_run(sha="a" * 40, event="pull_request", associations=None):
    return {
        "id": 4001, "name": "Integration Tests", "event": event,
        "head_sha": sha, "head_branch": "fix/compiler", "head_repository": copy.deepcopy(FORK),
        "repository": copy.deepcopy(REPO), "pull_requests": associations or [],
        "created_at": "2026-10-07T08:00:00Z", "run_started_at": "2026-10-07T08:00:01Z",
        "updated_at": "2026-10-07T09:00:00Z", "status": "completed", "conclusion": "success",
        "run_attempt": 1, "html_url": "https://github.com/triton-lang/triton-ascend/actions/runs/4001",
        "display_title": "Fix compiler", "head_commit": {"id": sha, "message": "Fix compiler"},
    }


def pull(number, sha="a" * 40, repo=FORK, created="2026-10-01T00:00:00Z", closed=None):
    return {
        "number": number, "id": 10000 + number, "title": f"Compiler change {number}",
        "url": f"https://api.github.com/repos/triton-lang/triton-ascend/pulls/{number}",
        "html_url": f"https://github.com/triton-lang/triton-ascend/pull/{number}",
        "created_at": created, "updated_at": "2026-10-07T09:00:00Z", "closed_at": closed,
        "merged_at": None, "state": "closed" if closed else "open",
        "user": {"login": repo["owner"]["login"]},
        "head": {"sha": sha, "ref": "fix/compiler", "label": repo["owner"]["login"] + ":fix/compiler",
                 "repo": copy.deepcopy(repo), "user": copy.deepcopy(repo["owner"])},
        "base": {"sha": "b" * 40, "ref": "main", "repo": copy.deepcopy(REPO)},
    }


class FakeAPI:
    """Supply GitHub-shaped responses; query filtering is part of the fake API boundary."""
    def __init__(self, pulls, commits=None, failure=None, history=None, comparisons=None):
        self.pulls = {p["number"]: copy.deepcopy(p) for p in pulls}
        self.commits = commits or {}
        self.failure = failure
        self.history = history or {}
        self.comparisons = comparisons or {}

    def force_push_history(self, number):
        if self.failure:
            raise self.failure
        return copy.deepcopy(self.history.get(number, []))

    def response(self, request):
        if self.failure:
            raise self.failure
        parsed = urlsplit(request)
        path = parsed.path
        if path.startswith("/compare/"):
            key = path.removeprefix("/compare/")
            return copy.deepcopy(self.comparisons.get(key, {"status": "diverged", "merge_base_commit": {"sha": "e" * 40}}))
        match = re.search(r"/pulls/(\d+)/commits$", path)
        if match:
            return [{"sha": sha} for sha in self.commits.get(int(match.group(1)), [])]
        match = re.search(r"/pulls/(\d+)$", path)
        if match:
            return copy.deepcopy(self.pulls[int(match.group(1))])
        if path.endswith("/pulls"):
            # The documented API can return multiple past PRs for a reused head branch.
            query = parse_qs(parsed.query)
            result = list(self.pulls.values())
            if "head" in query:
                result = [p for p in result if p["head"]["label"] == query["head"][0]]
            if query.get("state") == ["open"]:
                result = [p for p in result if p["state"] == "open"]
            return copy.deepcopy(result)
        raise AssertionError(f"Unexpected GitHub API request: {request}")

    def get(self, path):
        return self.response(path), {}

    def pages(self, path, field=None):
        result = self.response(path)
        return result[field] if field else result


class PRIdentityTests(unittest.TestCase):
    def test_fork_run_with_empty_association_resolves_exact_source_and_sha(self):
        result = PRResolver(FakeAPI([pull(42)])).resolve(action_run())
        self.assertEqual(result["pr"], 42)
        self.assertEqual(result["pr_url"], "https://github.com/triton-lang/triton-ascend/pull/42")
        self.assertEqual(result["pr_title"], "Compiler change 42")
        self.assertEqual(result["base_branch"], "main")
        self.assertEqual(result["head_sha"], "a" * 40)
        self.assertTrue(result["pr_evidence"]["method"])

    def test_reused_branch_selects_current_sha_not_first_or_nearest_pr(self):
        candidates = [pull(40, "c" * 40, closed="2026-10-03T00:00:00Z"), pull(41),
                      pull(42, "d" * 40, created="2026-10-07T07:59:00Z")]
        result = PRResolver(FakeAPI(candidates)).resolve(action_run())
        self.assertEqual(result["pr"], 41)

    def test_shared_head_on_two_prs_is_ambiguous(self):
        with self.assertRaises(ValueError):
            PRResolver(FakeAPI([pull(41), pull(42)])).resolve(action_run())

    def test_older_run_matches_pr_commit_history_and_retains_original_sha(self):
        api = FakeAPI([pull(42, "c" * 40)], commits={42: ["a" * 40, "c" * 40]})
        result = PRResolver(api).resolve(action_run())
        self.assertEqual(result["pr"], 42)
        self.assertEqual(result["head_sha"], "a" * 40)

    def test_sparse_run_association_is_hydrated_with_title_and_target_branch(self):
        result = PRResolver(FakeAPI([pull(42)])).resolve(action_run(associations=[{"number": 42}]))
        self.assertEqual(result["pr"], 42)
        self.assertEqual(result["pr_title"], "Compiler change 42")
        self.assertEqual(result["base_branch"], "main")
        self.assertEqual(result["pr_url"], "https://github.com/triton-lang/triton-ascend/pull/42")

    def test_direct_historical_association_retains_its_head_not_current_head(self):
        historical = {"number": 42, "head": {"sha": "a" * 40, "ref": "fix/compiler", "repo": FORK}}
        result = PRResolver(FakeAPI([pull(42, "c" * 40)])).resolve(action_run(associations=[historical]))
        self.assertEqual(result["head_sha"], "a" * 40)
        self.assertEqual(result["pr"], 42)

    def test_target_event_base_sha_is_not_silently_replaced_by_latest_pr_head(self):
        with self.assertRaises(ValueError):
            PRResolver(FakeAPI([pull(42)])).resolve(action_run("b" * 40, event="pull_request_target"))

    def test_same_sha_in_another_fork_does_not_establish_pr_identity(self):
        with self.assertRaises(ValueError):
            PRResolver(FakeAPI([pull(42, repo=OTHER_FORK)])).resolve(action_run())

    def test_future_pr_cannot_match_an_earlier_run(self):
        with self.assertRaises(ValueError):
            PRResolver(FakeAPI([pull(42, created="2026-10-08T00:00:00Z")])).resolve(action_run())

    def test_matching_title_and_time_without_sha_evidence_is_unresolved(self):
        candidate = pull(42, "c" * 40, created="2026-10-07T07:59:59Z")
        candidate["title"] = "Fix compiler"
        with self.assertRaises(ValueError):
            PRResolver(FakeAPI([candidate])).resolve(action_run())

    def test_metadata_api_failure_is_propagated_instead_of_publishing_unknown(self):
        with self.assertRaisesRegex(RuntimeError, "rate limited"):
            PRResolver(FakeAPI([pull(42)], failure=RuntimeError("rate limited"))).resolve(
                action_run(associations=[{"number": 42}]))

    def test_force_push_before_commit_recovers_sha_removed_from_current_commits(self):
        api = FakeAPI([pull(42, "c" * 40)], commits={42: ["c" * 40]}, history={42: [{
            "createdAt": "2026-10-07T09:00:00Z",
            "beforeCommit": {"oid": "a" * 40}, "afterCommit": {"oid": "c" * 40},
        }]})
        result = PRResolver(api).resolve(action_run())
        self.assertEqual(result["pr"], 42)
        self.assertEqual(result["head_sha"], "a" * 40)
        self.assertEqual(result["pr_title"], "Compiler change 42")
        self.assertTrue(result["pr_evidence"]["method"])

    def test_force_push_after_commit_recovers_sha_absent_from_current_commits(self):
        api = FakeAPI([pull(42, "c" * 40)], commits={42: ["c" * 40]}, history={42: [{
            "createdAt": "2026-10-07T07:59:00Z",
            "beforeCommit": {"oid": "d" * 40}, "afterCommit": {"oid": "a" * 40},
        }]})
        result = PRResolver(api).resolve(action_run())
        self.assertEqual(result["pr"], 42)
        self.assertEqual(result["head_sha"], "a" * 40)

    def test_reused_branch_with_unrelated_force_push_history_remains_unresolved(self):
        api = FakeAPI([pull(41, "c" * 40), pull(42, "d" * 40)],
                      commits={41: ["c" * 40], 42: ["d" * 40]}, history={
                          41: [{"createdAt": "2026-10-07T09:00:00Z",
                                "beforeCommit": {"oid": "e" * 40}, "afterCommit": {"oid": "c" * 40}}],
                          42: [{"createdAt": "2026-10-07T09:00:00Z",
                                "beforeCommit": {"oid": "f" * 40}, "afterCommit": {"oid": "d" * 40}}],
                      })
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

    def test_force_push_after_commit_event_after_run_does_not_establish_identity(self):
        api = FakeAPI([pull(42, "c" * 40)], commits={42: ["c" * 40]}, history={42: [{
            "createdAt": "2026-10-07T09:00:00Z",
            "beforeCommit": {"oid": "d" * 40}, "afterCommit": {"oid": "a" * 40},
        }]})
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

    def test_force_push_before_commit_event_before_run_does_not_establish_identity(self):
        api = FakeAPI([pull(42, "c" * 40)], commits={42: ["c" * 40]}, history={42: [{
            "createdAt": "2026-10-07T07:00:00Z",
            "beforeCommit": {"oid": "a" * 40}, "afterCommit": {"oid": "c" * 40},
        }]})
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

    def test_same_source_and_force_push_sha_on_two_prs_is_ambiguous(self):
        api = FakeAPI([pull(41, "c" * 40), pull(42, "d" * 40)], history={
            41: [{"createdAt": "2026-10-07T09:00:00Z",
                  "beforeCommit": {"oid": "a" * 40}, "afterCommit": {"oid": "c" * 40}}],
            42: [{"createdAt": "2026-10-07T09:00:00Z",
                  "beforeCommit": {"oid": "a" * 40}, "afterCommit": {"oid": "d" * 40}}],
        })
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())



class HistoricalAncestorTests(unittest.TestCase):
    def test_all_34_runs_from_failed_scheduled_refresh_resolve(self):
        fixture=json.loads((Path(__file__).parent/"fixtures/historical-ancestry.json").read_text(encoding="utf-8"))
        api=FakeAPI(list(fixture["pulls"].values()),
                    history={int(n):events for n,events in fixture["histories"].items()},
                    comparisons=fixture["comparisons"])
        resolver=PRResolver(api)
        self.assertEqual(len(fixture["runs"]),34)
        expected={"feature/simd-simt-compile-mode-sync-main-v2":2545,
                  "origin":2532,"gather-in-graph-opt-v3":2244,"fix/q3-scan-mode":2480}
        for run in fixture["runs"]:
            with self.subTest(run=run["id"]):
                result=resolver.resolve(run)
                self.assertEqual(result["pr"],expected[run["head_branch"]])
                self.assertEqual(result["head_sha"],run["head_sha"])
                self.assertIn("ancestry",result["pr_evidence"]["method"])

    def fixture(self, status="ahead", merge_base=None):
        old="a" * 40; anchor="d" * 40
        event={"createdAt":"2026-10-07T09:00:00Z",
               "beforeCommit":{"oid":anchor},"afterCommit":{"oid":"c" * 40}}
        comparisons={old+"..."+"b" * 40:{"status":"diverged","merge_base_commit":{"sha":"e" * 40}},
                     old+"..."+anchor:{"status":status,
            "merge_base_commit":{"sha":merge_base or old}}}
        return FakeAPI([pull(42,"c" * 40)],history={42:[event]},comparisons=comparisons)

    def test_intermediate_push_removed_by_force_push_retains_original_identity(self):
        result=PRResolver(self.fixture()).resolve(action_run())
        self.assertEqual(result["pr"],42)
        self.assertEqual(result["head_sha"],"a" * 40)
        self.assertEqual(result["pr_evidence"]["force_push_event"]["beforeCommit"]["oid"],"d" * 40)

    def test_target_run_with_real_fork_head_can_use_historical_ancestry(self):
        result=PRResolver(self.fixture()).resolve(action_run(event="pull_request_target"))
        self.assertEqual(result["head_sha"],"a" * 40)

    def test_diverged_history_cannot_establish_identity(self):
        with self.assertRaises(ValueError):
            PRResolver(self.fixture(status="diverged")).resolve(action_run())

    def test_wrong_merge_base_cannot_establish_identity(self):
        with self.assertRaises(ValueError):
            PRResolver(self.fixture(merge_base="e" * 40)).resolve(action_run())

    def test_base_branch_ancestor_cannot_be_mistaken_for_pr_head(self):
        api=self.fixture()
        api.comparisons["a" * 40+"..."+"b" * 40]={"status":"ahead","merge_base_commit":{"sha":"a" * 40}}
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run(event="pull_request_target"))

    def test_history_before_run_does_not_prove_later_head(self):
        api=self.fixture()
        api.history[42][0]["createdAt"]="2026-10-07T07:00:00Z"
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

    def test_historical_match_saves_compare_proof_for_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            result=PRResolver(self.fixture(),directory).resolve(action_run())
            proofs=list(Path(directory).glob("compare-*.json"))
            self.assertEqual(len(proofs),2)
            statuses={json.loads(p.read_text(encoding="utf-8"))["status"] for p in proofs}
            self.assertEqual(statuses,{"ahead","diverged"})
            saved=json.loads((Path(directory)/"4001.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["head_sha"],"a" * 40)
            self.assertEqual(saved["pr_evidence"],result["pr_evidence"])

    def test_compare_api_failure_is_propagated(self):
        api=self.fixture()
        original=api.get
        def get(path):
            if path.startswith("/compare/"): raise RuntimeError("comparison unavailable")
            return original(path)
        api.get=get
        with self.assertRaisesRegex(RuntimeError,"comparison unavailable"):
            PRResolver(api).resolve(action_run())

    def test_missing_comparison_status_blocks_publication(self):
        api=self.fixture()
        api.comparisons["a" * 40+"..."+"d" * 40]={}
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

    def test_missing_base_comparison_status_blocks_publication(self):
        api=self.fixture()
        api.comparisons["a" * 40+"..."+"b" * 40]={}
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

    def test_two_pr_histories_containing_old_sha_remain_ambiguous(self):
        api=self.fixture()
        api.pulls[43]=pull(43,"f" * 40)
        api.history[43]=copy.deepcopy(api.history[42])
        with self.assertRaises(ValueError):
            PRResolver(api).resolve(action_run())

if __name__ == "__main__":
    unittest.main()
