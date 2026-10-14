"""Resolve PR identities from explicit run evidence or fork/ref/commit evidence."""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


class PRResolver:
    def __init__(self, api, evidence_dir=None):
        self.api=api
        self.evidence_dir=Path(evidence_dir) if evidence_dir else None
        self.cache={}

    def read(self, path, many=False):
        key=(path,many)
        if key not in self.cache:
            self.cache[key]=self.api.pages(path) if many else self.api.get(path)[0]
        return self.cache[key]

    @staticmethod
    def same_source(run, pr):
        head=pr.get("head") or {}
        repo=head.get("repo") or {}
        source=run.get("head_repository") or {}
        if run.get("head_branch") and head.get("ref")!=run["head_branch"]: return False
        if source.get("id") and repo.get("id"): return source["id"]==repo["id"]
        if source.get("full_name") and repo.get("full_name"):
            return source["full_name"].lower()==repo["full_name"].lower()
        return False

    @staticmethod
    def existed(run, pr):
        if not pr.get("created_at") or not run.get("created_at"): return True
        parse=lambda x:datetime.fromisoformat(x.replace("Z","+00:00"))
        return parse(pr["created_at"])<=parse(run["created_at"])

    def compare(self, sha, anchor):
        result=self.read(f"/compare/{sha}...{anchor}?per_page=1")
        if self.evidence_dir:
            self.evidence_dir.mkdir(parents=True,exist_ok=True)
            (self.evidence_dir/f"compare-{sha}-{anchor}.json").write_text(
                json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        return result

    def historical_head(self, run, number, base_sha=None):
        key=("force_push_history",number)
        if key not in self.cache:
            self.cache[key]=self.api.force_push_history(number)
            if self.evidence_dir:
                self.evidence_dir.mkdir(parents=True,exist_ok=True)
                (self.evidence_dir/f"pr-{number}-force-pushes.json").write_text(
                    json.dumps(self.cache[key],ensure_ascii=False,indent=2),encoding="utf-8")
        if not run.get("created_at"): return None
        parse=lambda x:datetime.fromisoformat(x.replace("Z","+00:00"))
        created=parse(run["created_at"])
        for event in self.cache[key]:
            if not isinstance(event,dict) or not event.get("createdAt"):
                raise ValueError(f"PR {number} force-push event incomplete")
            when=parse(event["createdAt"])
            for field,valid in (("beforeCommit",created<=when),("afterCommit",when<=created)):
                if valid and (event.get(field) or {}).get("oid")==run.get("head_sha"):
                    return {"matched_field":field,**event}
        # Ordinary pushes between force pushes are not timeline endpoints.
        # Prove membership in a later pre-force-push head's ancestry.
        sha=run.get("head_sha")
        for event in self.cache[key]:
            anchor=(event.get("beforeCommit") or {}).get("oid")
            if not anchor or parse(event["createdAt"]) < created: continue
            comparison=self.compare(sha,anchor)
            if comparison.get("status") not in ("ahead","identical"): continue
            if (comparison.get("merge_base_commit") or {}).get("sha")!=sha: continue
            # Shared upstream ancestry does not prove a PR head; target-event
            # runs can carry the base SHA. Missing proof still blocks publishing.
            if not base_sha: continue
            base=self.compare(sha,base_sha)
            if base.get("status") not in ("behind","diverged"): continue
            return {"matched_field":"beforeCommit.ancestor","matched_sha":sha,**event}
        return None

    def resolve(self, run):
        linked=run.get("pull_requests") or []
        explicit={p["number"]:p for p in linked if p.get("number")}
        candidates=[]
        if explicit:
            candidates=[self.read(f"/pulls/{n}") for n in explicit]
        else:
            source=run.get("head_repository") or {}
            owner=(source.get("owner") or {}).get("login") or source.get("full_name","").split("/")[0]
            if owner and run.get("head_branch"):
                head=quote(owner+":"+run["head_branch"],safe="")
                candidates=self.read(f"/pulls?state=all&head={head}",many=True)
            if not candidates:
                candidates=self.read(f"/commits/{run['head_sha']}/pulls",many=True)
        matches=[]
        for pr in candidates:
            number=pr.get("number")
            if not number or not self.existed(run,pr): continue
            is_linked=number in explicit
            if not is_linked and not self.same_source(run,pr): continue
            sha=run.get("head_sha")
            snapshot=((explicit.get(number) or {}).get("head") or {}).get("sha")
            if is_linked and snapshot:
                matches.append((pr,snapshot,"run.pull_requests.head.sha",None));continue
            if sha and sha==(pr.get("head") or {}).get("sha"):
                matches.append((pr,sha,"source_repository+branch+head_sha",None));continue
            if sha and any(c.get("sha")==sha for c in self.read(f"/pulls/{number}/commits",many=True)):
                matches.append((pr,sha,"source_repository+branch+pr_commit_history",None));continue
            history=self.historical_head(run,number,(pr.get("base") or {}).get("sha")) if sha else None
            if history:
                method="source_repository+branch+force_push_history"
                if history["matched_field"]=="beforeCommit.ancestor": method+="+ancestry"
                matches.append((pr,sha,method,history))
        # Never guess from title, nearest creation time, or the first branch match.
        matches={p[0]["number"]:p for p in matches}
        if len(matches)!=1:
            diagnostic={"run_id":run.get("id"),"head_sha":run.get("head_sha"),"head_branch":run.get("head_branch"),"candidates":[p.get("number") for p in candidates],"matches":list(matches)}
            self.save(run,diagnostic)
            raise ValueError(f"PR identity unresolved/ambiguous: {diagnostic}")
        pr,sha,method,history=next(iter(matches.values()))
        result={"pr":pr["number"],"pr_url":pr.get("html_url") or f"https://github.com/triton-lang/triton-ascend/pull/{pr['number']}",
                "pr_title":pr.get("title"),"base_branch":(pr.get("base") or {}).get("ref"),"head_sha":sha,
                "pr_evidence":{"method":method,"run_id":run.get("id"),"pr":pr["number"],"raw_run_sha":run.get("head_sha"),"resolved_head_sha":sha,
                               "source_repository":(pr.get("head",{}).get("repo") or {}).get("full_name"),"head_ref":(pr.get("head") or {}).get("ref")}}
        if history: result["pr_evidence"]["force_push_event"]=history
        if not result["pr_title"] or not result["base_branch"]:
            raise ValueError(f"PR {pr['number']} metadata incomplete")
        self.save(run,result)
        return result

    def save(self,run,value):
        if self.evidence_dir:
            self.evidence_dir.mkdir(parents=True,exist_ok=True)
            (self.evidence_dir/f"{run['id']}.json").write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
