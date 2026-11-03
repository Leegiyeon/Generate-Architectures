"""GitHub merged-PR 브랜치 안전 정리 (GitHub Actions GITHUB_TOKEN, no extra credentials).

Protect default/protected/open-PR/unmerged-work branches. Never force-push.
The apply step is opt-in; read-only plan and pure-selection logic are testable.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def find_prunable(branches, pull_requests, default_branch, repo_full_name):
    """Return safe candidates with exact matching merged PR head and unchanged tip."""
    defaults = [b for b in branches if b.get("name") == default_branch]
    if len(defaults) != 1:
        raise ValueError("기본 브랜치 정보가 없어 삭제 계획을 중단합니다.")
    open_heads = {
        p["head"]["ref"] for p in pull_requests
        if p.get("state") == "open" and
        (p.get("head", {}).get("repo") or {}).get("full_name") == repo_full_name
    }
    merged_heads = {}
    for p in pull_requests:
        head = p.get("head") or {}
        if (p.get("merged_at") and p.get("state") == "closed" and
                (head.get("repo") or {}).get("full_name") == repo_full_name and
                p.get("base", {}).get("ref") == default_branch):
            merged_heads.setdefault(head["ref"], set()).add(head["sha"])
    targets = []
    for b in branches:
        name = b.get("name", "")
        if name == default_branch or b.get("protected", False) or name in open_heads:
            continue
        sha = (b.get("commit") or {}).get("sha")
        # Never delete arbitrary branches merely because they equal main. Only previously
        # merged PR heads are eligible; manually created/unmerged branches are preserved.
        if sha and sha in merged_heads.get(name, set()):
            targets.append({"branch": name, "sha": sha, "reason": "merged_PR_head_unchanged"})
    return sorted(targets, key=lambda x: x["branch"])


class GitHubClient:
    def __init__(self, token, repo):
        if not token or not repo or "/" not in repo:
            raise ValueError("GH_TOKEN / GITHUB_REPOSITORY 필요")
        self.token, self.repo = token, repo

    def request(self, path, method="GET"):
        url = "https://api.github.com/repos/" + self.repo + ("/" + path if path else "")
        req = Request(url, method=method, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Generate-Architectures-Branch-Pruner",
        })
        with urlopen(req, timeout=25) as res:
            raw = res.read()
        return json.loads(raw) if raw else None

    def paged(self, endpoint):
        page = 1
        records = []
        while True:
            if page > 50:
                raise ValueError("브랜치/PR 페이지가 많아 안전하게 중단했습니다.")
            chunk = self.request(endpoint + ("&" if "?" in endpoint else "?") +
                                 "per_page=100&page=" + str(page))
            if not isinstance(chunk, list):
                raise ValueError("GitHub API 응답이 리스트가 아닙니다.")
            records.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return records

    def branch(self, name):
        return self.request("branches/" + quote(name, safe="/"))

    def delete_branch(self, name):
        return self.request("git/refs/heads/" + quote(name, safe="/"), method="DELETE")


def prune(repo, token, *, apply=False):
    client = GitHubClient(token, repo)
    meta = client.request("")
    if meta.get("full_name") != repo or meta.get("default_branch") != "main":
        raise ValueError("예상하지 않은 저장소/기본 브랜치여서 실행을 중단합니다.")
    branches = client.paged("branches")
    prs = client.paged("pulls?state=all")
    eligible = find_prunable(branches, prs, meta["default_branch"], repo)
    print("보호/미병합/열린 PR 브랜치는 건드리지 않습니다.")
    print("삭제 후보 " + str(len(eligible)) + "개: " +
          ", ".join(x["branch"] for x in eligible))
    if not apply:
        print("미리보기 모드: 삭제하지 않았습니다.")
        return {"candidates": eligible, "deleted": [], "skipped": []}
    deleted, skipped = [], []
    for item in eligible:
        name = item["branch"]
        # Recheck changed heads and open PRs immediately before deletion.
        current = client.branch(name)
        if current.get("protected") or current.get("commit", {}).get("sha") != item["sha"]:
            skipped.append(name + " (보호/커밋 변경)")
            continue
        live_prs = client.paged("pulls?state=open&head=" + quote(repo.split("/")[0] +
                               ":" + name, safe=":"))
        if any((x.get("head", {}).get("repo") or {}).get("full_name") == repo
               and x.get("head", {}).get("ref") == name for x in live_prs):
            skipped.append(name + " (새 PR 감지)")
            continue
        try:
            client.delete_branch(name)
            deleted.append(name)
            print("삭제 완료: " + name)
        except HTTPError as exc:
            skipped.append(name + " (HTTP " + str(exc.code) + ")")
    print("정리 결과: 삭제 " + str(len(deleted)) + "개, 건너뜀 " + str(len(skipped)) + "개")
    if skipped:
        print("수동 확인 대상: " + "; ".join(skipped))
    return {"candidates": eligible, "deleted": deleted, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="보호된/열린/커밋 변경 브랜치는 건너뛰고 삭제 실행")
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != "Leegiyeon/Generate-Architectures":
        sys.exit("본 저장소에서만 실행할 수 있습니다.")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        sys.exit("main 브랜치에서만 실행할 수 있습니다.")
    result = prune(os.environ["GITHUB_REPOSITORY"], os.environ.get("GH_TOKEN"),
                   apply=args.apply)
    # Cleanup is best effort: if permissions are disabled, don't invent deletion success.
    if result["skipped"]:
        sys.exit(1)
