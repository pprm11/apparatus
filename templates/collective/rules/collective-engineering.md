# Team engineering rules (collective)

Short version, always loaded. Reasons and the full procedure: skill `collective-engineering-rules`.

- A red check blocks the merge. No exception, no rerun until green, no weaker branch protection. A false
  positive in a gate gets its own PR with a regression test. The author never approves their own PR.
- No push to a PR after approval, except a merge-queue rejection, a conflict or broken CI. Other fixes go in a
  follow-up PR stacked on it.
- A review comment or recurring finding becomes a lint or a test that would have caught it.
- Parallel sessions on one repo: one writer per file; check `git status` and open sessions first.
- Stacked PRs: base is the parent's branch; merge the parent into the child, never rebase or force-push;
  line 1 of the PR body declares the stack; the parent enters by merge commit, not squash.
