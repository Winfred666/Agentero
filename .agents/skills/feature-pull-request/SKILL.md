---
name: feature-pull-request
description: >-
  Prepare an Agentero feature-only branch for an upstream pull request, verify
  it on both clean and macOS integration histories, push it to the fork, and
  draft a Chinese GitHub PR in Chrome without submitting it.
---

# Feature Pull Request

Prepare a reviewable upstream contribution while keeping local macOS test
scaffolding out of the pull request.

## Synchronize first

Invoke `rebase-feat-to-upstream-main` before PR preparation. The resulting
topology must have a clean `main`, a feature-only `feat/<topic>` based on
`main`, a separate `mac-dev`, and a disposable `mac-test/<topic>` integration
branch.

Do not continue when synchronization, range comparison, or relevant tests are
unresolved. Pushing and browser actions still require authorization in the
current request; authorization from an older run is not reusable.

## Select the PR head

1. Inspect `git log main..feat/<topic>` and `git diff main...feat/<topic>`.
   Every commit and changed file must belong to the upstream feature.
2. Prefer the clean feature branch itself as the PR head. Do not cherry-pick it
   into `main`.
3. Only when the feature branch contains non-upstreamable commits, create a
   clean `pr/<topic>` from `main` and cherry-pick the explicitly identified
   feature commits into that branch. Never include macOS scaffold, local
   workflow-skill, integration-merge, or unrelated commits.
4. Check the repository for a corresponding issue. Reference it in the commit
   or PR text according to `AGENTS.md`; do not claim an issue is fully fixed
   unless the change actually closes it.

## Verify the contribution

1. Run feature-specific tests on the feature-only PR head.
2. Run the appropriate CLI/UI/app build and behavioral checks on
   `mac-test/<topic>`, where the PR head is integrated with `mac-dev`.
3. Inspect the final PR diff against `upstream/main`, not against the local test
   branch. Confirm the diff contains no macOS scaffold or workflow-skill files.
4. Record the exact commands and outcomes. Distinguish compilation, automated
   tests, rendered UI inspection, and real behavior; do not use one as evidence
   for another.

## Push the PR head

When explicitly authorized, push the PR head to the identically named branch on
`origin`. Use an ordinary push for a new branch. If synchronization rebased an
existing remote branch, use only a lease tied to its fetched old SHA. Never
push the PR head to `origin/main` or directly to `upstream`.

Verify the remote head SHA after pushing before opening GitHub.

## Draft the upstream PR in Chrome

1. Use the Chrome control skill and the user's existing signed-in session.
2. Open the compare page for `upstream/main` against the pushed fork branch.
   Derive repository owners and branch names from the verified remotes rather
   than assuming the current page is correct.
3. Confirm the visible base is upstream `main` and the head is the fork's PR
   branch. Stop if GitHub reports the wrong repositories, branches, or diff.
4. Follow the upstream repository's PR template when present. Write the PR body
   in Chinese while preserving code identifiers, paths, issue numbers, and test
   commands. Cover the problem, focused changes, verification, and meaningful
   risks or limitations. Keep the title concise and consistent with upstream
   conventions.
5. Review the rendered title, body, commit list, and file diff. Do not click the
   final **Create pull request** or submit button. Leave the completed draft in
   Chrome for the user to review and submit manually.

Report the local and remote head SHAs, test evidence, compare target, and the
fact that no pull request was submitted.
