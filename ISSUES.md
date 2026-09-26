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

## Issue 2 (RESOLVED upstream): CHEMCLAW_NOTE_REPO_DIR must be set for note writing to work (missing from deployment docs)

**Status: closed by Chemclaw3 PR #450 (2026-09-26).** The consumer is no longer ELN sync — an ELN
transcription is data and writes no note — but `GitNoteWriter`, the one knowledge write path. The
Chemclaw3 runbook (`docs/guides/runbook.md`) now states what the notes repo needs, each requirement
driven against the writer: a dedicated clone with a real `.git`, checked out on
`CHEMCLAW_NOTE_BASE_BRANCH`, a remote that already has that branch, a seeded `knowledge/`, and a
committer identity. A missing remote or base branch now fails as a retryable `GitRemoteError`
rather than silently. "Must not be shallow" was measured false and dropped.

Two parts stay open *upstream*, not here: nothing in the chart supplies a git committer identity,
so a container's every commit fails with `Author identity unknown` (a Chemclaw3 `BACKLOG.md` row);
and `/readyz` still does not probe the note repo — declined for now, because checking the remote
needs a network fetch and the worker's readiness path does no I/O. The report below is kept for why
it was filed.

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
silent. In a 190-probe live run **every** note write failed — 14 attempts, 0 notes written —
because the git note writer begins with `git fetch <git_remote> <note_base_branch>`, defaulting to
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

**Still live, re-verified 2026-09-07 — and only the name of the consumer changed.** The paragraphs
above were written while notes reached the graph through a PR gate, and that gate is gone
(`D-2026-09-05-the-gate-follows-behaviour-not-knowledge`): a note is now committed straight onto
the base branch and pushed, by `chemclaw.kg.git_writer.GitNoteWriter` — no `note/<id>` branch and
no human merge. **None of the three requirements below moved**, because they were never properties
of the gate: the writer still reads `note_base_branch` and `git_remote`, still opens with
`git fetch <remote> <base>`, and still pushes that base branch. What did change is that the third
requirement is now checked with an error of its own — a checkout parked on any branch but the base
is refused by name rather than failing somewhere further down. The class in the traceback above is
today's `GitWriteError` (it was `GitSubmitError`, then a bare `RuntimeError`); the wording of its
message has been rewritten since, so grep for `note_repo_dir` rather than for the sentence.

The one word that *was* stale is "PR-gate", and correcting it does not weaken this report: there is
now no review step between the agent and the graph, so a misconfigured notes repo is a knowledge
write path that is silently dead, with nothing downstream that would have caught it.

Two upstream defects made this hard to diagnose, both fixed on 2026-08-02: `GitSubmitError` was a
`RuntimeError` rather than a `ChemclawError`, so the agent was told only "Error: Function failed."
and retried five times permuting its *arguments*; and `/readyz` does not probe the note repo, so a
deployment whose only knowledge-write path is dead still reports ready.
