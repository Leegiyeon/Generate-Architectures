"""병합 후 자동 브랜치 정리가 안전하게 대상을 선택하는지 검증."""
import unittest
from scripts.branch_cleanup import find_prunable


REPO = "Leegiyeon/Generate-Architectures"


def branch(name, sha, protected=False):
    return {"name": name, "commit": {"sha": sha}, "protected": protected}


def pr(name, sha, *, state="closed", merged=True, from_repo=REPO, base="main"):
    return {
        "head": {"ref": name, "sha": sha, "repo": {"full_name": from_repo}},
        "base": {"ref": base}, "state": state,
        "merged_at": "2026-11-03T07:00:00Z" if merged else None,
    }


class BranchCleanupTests(unittest.TestCase):
    def setUp(self):
        self.branches = [
            branch("main", "main-current"),
            branch("feat/merged", "head-1"),
            branch("docs/stale", "head-2"),
            branch("feat/unmerged", "work-3"),
            branch("feat/new-commit-after-merge", "changed"),
            branch("feat/active-pr", "active"),
            branch("feat/protected", "protected", True),
            branch("feat/fork-pr", "fork-head"),
            branch("fix/non-pr-even-if-main-sha", "main-current"),
        ]
        self.prs = [
            pr("feat/merged", "head-1"), pr("docs/stale", "head-2"),
            pr("feat/new-commit-after-merge", "original-sha"),
            pr("feat/unmerged", "work-3", merged=False),
            pr("feat/active-pr", "active", state="open", merged=False),
            pr("feat/protected", "protected"),
            pr("feat/fork-pr", "fork-head", from_repo="someone/other-repo"),
        ]

    def test_only_unchanged_same_repo_merged_pr_heads_deleted(self):
        targets = find_prunable(self.branches, self.prs, "main", REPO)
        self.assertEqual([x["branch"] for x in targets],
                         ["docs/stale", "feat/merged"])
        self.assertTrue(all(x["reason"] == "merged_PR_head_unchanged"
                            for x in targets))

    def test_default_branch_never_deleted_even_if_merged_pr_claims_main(self):
        targets = find_prunable(self.branches, self.prs + [pr("main","main-current")],
                               "main", REPO)
        self.assertNotIn("main", [x["branch"] for x in targets])

    def test_fails_closed_without_default_branch_info(self):
        with self.assertRaises(ValueError):
            find_prunable(self.branches[1:], self.prs, "main", REPO)

    def test_merged_pr_with_open_pr_same_branch_is_not_deleted(self):
        prs = self.prs + [pr("feat/merged", "head-1", state="open", merged=False)]
        targets = find_prunable(self.branches, prs, "main", REPO)
        self.assertNotIn("feat/merged", [x["branch"] for x in targets])

    def test_old_sha_changed_after_merge_and_unmerged_work_preserved(self):
        targets = find_prunable(self.branches, self.prs, "main", REPO)
        found = {x["branch"] for x in targets}
        for name in ("feat/unmerged", "feat/new-commit-after-merge",
                     "feat/protected", "feat/fork-pr", "feat/active-pr",
                     "fix/non-pr-even-if-main-sha"):
            self.assertNotIn(name, found)


if __name__ == "__main__":
    unittest.main()
