# Open Issues — Chemclaw3_mock

File these at: https://github.com/8fqycwdt8v-oss/Chemclaw3_mock/issues/new

---

## Issue 1 (RESOLVED — not reproducible): Bare azide anion `[N-]=[N+]=[N-]`

**Status: closed.** Re-tested against Chemclaw3 `main` on 2026-08-02 during a 190-probe live run.
The bare azide anion and sodium azide both fire, via a `non-carbon-azide` rule that exists in
`src/chemclaw/science/safety/rules.yaml` specifically for the sanitised salt form:

```
screen_structure("[N-]=[N+]=[N-]")        -> ['non-carbon-azide']
screen_structure("[N-]=[N+]=[N-].[Na+]")  -> ['non-carbon-azide']
screen_structure("CCCN=[N+]=[N-]")        -> ['organic-azide']
```

Either the rule was added after this issue was filed, or the original test hit a different
configuration. Leaving the report here rather than deleting it, because the *reason* it was filed
was sound and the same live run confirmed four genuinely silent rules of exactly this shape —
`peroxide` missed sodium peroxide, `hydrazine` missed UDMH, `n-halamine` missed chloramine-T, and
`complex-hydride-with-chlorinated-solvent` missed 1,2-dichloroethane. All four are fixed upstream.

## Issue 2: CHEMCLAW_NOTE_REPO_DIR must be set for ELN sync to work (missing from deployment docs)

When the `ElnSyncWorkflow` runs via Temporal, it fails with:

```
GitSubmitError: note_repo_dir '.' resolves to /home/runner/workspace/services/chemclaw
— the checkout this process is running from. Set CHEMCLAW_NOTE_REPO_DIR to a dedicated clone.
```

The default `CHEMCLAW_NOTE_REPO_DIR="."` is always wrong in any deployment (it would destroy the
service's own working tree). The deployment runbook / README should make this a required variable
and explain what the notes repo needs (a git repo with at minimum an initial commit; no specific
branch or remote required for dev).

**Workaround applied:** Created `/services/chemclaw-notes-repo` as a fresh `git init` repo and
set `CHEMCLAW_NOTE_REPO_DIR` to its absolute path.

**Confirmed and extended, 2026-08-02.** A fresh `git init` is *not* sufficient, and the failure is
silent. In a 190-probe live run **every** PR-gate write failed — 14 attempts, 0 notes proposed —
because `GitNoteSubmitter` begins with `git fetch <git_remote> <note_base_branch>`, defaulting to
`origin` and `main`. A bare `git init` clone has no `origin`, and `git init` names the branch
`master` on many installs, so both halves miss.

The notes repo needs three things, all of which belong in the runbook:

1. a commit (as filed),
2. a configured `origin` remote — a local bare repo is enough: `git init --bare /path/notes-origin`
   then `git remote add origin /path/notes-origin && git push -u origin HEAD`,
3. a branch whose name matches `CHEMCLAW_NOTE_BASE_BRANCH` (default `main`).

It should also be seeded with the existing `knowledge/` tree, because Chemclaw3 resolves
`knowledge_path` as `note_repo_dir / knowledge_dir` — point it at an empty clone and every reader
sees an empty graph, with no error.

Two upstream defects made this hard to diagnose, both fixed on 2026-08-02: `GitSubmitError` was a
`RuntimeError` rather than a `ChemclawError`, so the agent was told only "Error: Function failed."
and retried five times permuting its *arguments*; and `/readyz` does not probe the note repo, so a
deployment whose only knowledge-write path is dead still reports ready.
