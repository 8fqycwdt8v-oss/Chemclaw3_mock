# Open Issues — Chemclaw3_mock

File these at: https://github.com/8fqycwdt8v-oss/Chemclaw3_mock/issues/new

---

## Issue 1: Bare azide anion [N-]=[N+]=[N-] not flagged by structural hazard screen

**Repo:** Chemclaw3 (the main backend, not mock — but discovered via mock integration testing)

When the Chemclaw3 agent's `screen_hazards` tool is called with `[N-]=[N+]=[N-]` (bare azide
anion / sodium azide), no hazard flag is returned:

```
No rule matched in this screening
```

Diacetyl peroxide `CC(=O)OOC(C)=O` is correctly flagged HIGH SEVERITY (O–O bond).

The model's answer correctly caveated that "azides are well-known as shock-sensitive explosives"
— so the knowledge is present, but the structural rule set is missing the SMARTS pattern for the
ionic azide form.

**Expected:** HIGH SEVERITY flag for N=N=N / [N+]#[N-] / [N-]=[N+]=[N-] patterns.

**Note:** Organic azides (C–N3, SMARTS `[N;X1]=[N+]=[N-]` attached to carbon) may already be
covered; only the bare anion form was tested here.

---

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
