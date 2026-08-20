---
name: rebase-feat-to-upstream-main
description: >-
  Synchronize Agentero's upstream mirror, macOS scaffold branch, feature-only
  branches, disposable macOS test branches, and fork refs without mixing their
  histories. Use for cascaded upstream/main synchronization or before preparing
  an upstream pull request.
---

# Rebase Feature Work to Upstream Main

Keep four histories separate while updating the fork:

- `main`: a clean fast-forward mirror of `upstream/main`.
- `mac-dev`: macOS build/test scaffolding and local workflow skills only.
- `feat/<topic>`: upstreamable feature commits based directly on `main`.
- `mac-test/<topic>`: a disposable integration branch combining `mac-dev` and
  `feat/<topic>` for real CLI/UI/app testing.

Git cannot contain both `mac-dev` and `mac-dev/<topic>` refs, so always use the
`mac-test/<topic>` namespace for disposable integration branches.

## Safety invariants

- Never put feature or macOS scaffold commits on `main`.
- Never push any ref other than local `main` to `origin/main`.
- Never push to `upstream`; upstream changes go through a pull request.
- Never rebase, reset, delete, or switch away from a dirty worktree. Do not
  auto-stash user changes.
- Treat every linked worktree as part of the preflight. Stop if a branch to be
  rewritten is checked out elsewhere or has unexplained work.
- Use `--force-with-lease`, never `--force`, when an explicitly authorized push
  must update a previously published rebased branch.
- A request must explicitly authorize pushing before changing `origin`.

## Preflight

1. Read the repository `AGENTS.md`, `git status`, `git worktree list`, remotes,
   branch tracking, and the relevant commit graph.
2. Verify that `upstream` is the authoritative repository and `origin` is the
   user's fork. Stop if the roles are absent or ambiguous.
3. Resolve the feature branch and its matching `mac-test/<topic>` branch. Do not
   interpret every `feat/*` branch as in scope.
4. Record immutable pre-operation SHAs for `main`, `upstream/main`, `origin/main`,
   `mac-dev`, the feature branch, and the disposable test branch. Create
   temporary backup refs when history will be rewritten.
5. Record the ordered commit ranges for the macOS scaffold and feature work.
   If the feature branch contains macOS scaffold commits or a scaffold merge,
   split it before continuing: preserve the combined history as the disposable
   test branch and recover only feature commits onto a branch based on `main`.

## Synchronize the durable branches

1. Fetch both remotes:

   ```bash
   git fetch upstream main
   git fetch origin
   ```

2. Require local `main` to be an ancestor of `upstream/main`. Switch to `main`
   and run `git merge --ff-only upstream/main`. A divergent local `main` is a
   stop condition; do not rebase or discard it automatically.
3. Rebase `mac-dev` onto the updated `main`. Preserve only its recorded macOS
   scaffold and local-workflow commits. Compare the old and new series with
   `git range-diff`; investigate missing, duplicated, or materially changed
   patches before proceeding.
4. Rebase the selected `feat/<topic>` onto updated `main`, not onto `mac-dev`.
   Verify its feature-only series with `git range-diff` and inspect
   `git diff main...feat/<topic>` for leaked scaffold changes.
5. If a rebase conflict makes feature versus scaffold ownership ambiguous,
   abort that rebase and report the exact files. Do not guess across the layer
   boundary.

## Rebuild the disposable test branch

1. Inspect the existing `mac-test/<topic>` before replacing it. If it contains
   test-only commits that are not present on either durable branch, stop and
   classify them instead of deleting them.
2. Recreate `mac-test/<topic>` from the updated `mac-dev`.
3. Merge `feat/<topic>` with an explicit `--no-ff` integration merge. Do not
   copy feature commits into `mac-dev`.
4. Run the smallest relevant clean-feature tests plus the required real
   CLI/UI/app checks on the disposable integration branch. Report build success,
   rendered UI inspection, and real behavior separately.

## Verify and optionally sync the fork

Before pushing, verify:

- `main` equals `upstream/main`.
- `feat/<topic>` is based on `main` and does not contain `mac-dev` commits.
- `mac-dev` contains the expected scaffold series.
- `mac-test/<topic>` contains both durable branches through its integration
  merge.
- The worktree is clean and relevant tests passed.

When the current request explicitly authorizes remote synchronization:

1. Push `main:main` to `origin` as a fast-forward only.
2. Push `mac-dev`, `feat/<topic>`, and `mac-test/<topic>` to identically named
   refs on `origin`.
3. For an already published rebased branch, use a lease tied to the fetched old
   remote SHA. Stop if the lease fails; refetch and report instead of retrying
   with a broader force.
4. Fetch or inspect the remote refs and verify that every pushed SHA matches.

Finally remove only the temporary backup refs created by this run and restore
the original working branch, unless the user explicitly requested another final
checkout.
