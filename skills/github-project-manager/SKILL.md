---
name: github-project-manager
description: Manage GitHub as a project/task system by planning and syncing issues, pull requests, labels, milestones, and GitHub Projects. Use when users ask to turn implementation plans into tracked work, create/update project boards or roadmaps, keep issue/PR/project state aligned, define estimation fields, or set up GitHub-native automation for planning and execution.
---

# GitHub Project Manager

## Overview

Use this skill to convert implementation plans into a reproducible GitHub execution system and keep it synchronized over time.
Prefer `gh` CLI first, then use GitHub Actions for automation that cannot be expressed with built-in project workflows.

## Quick Usage

Use one of these prompts:
- `Use $github-project-manager to create tracked work from this implementation plan.`
- `Use $github-project-manager to sync issue/PR/project status for this repo.`
- `Use $github-project-manager to bootstrap GitHub Project tracking for this repo.`

## Workflow

### -1) Preflight and remediation

Run preflight before inference:

```bash
git remote -v
gh auth status -h github.com
gh repo view --json nameWithOwner,defaultBranchRef,isPrivate
```

If preflight fails, branch explicitly:
- `gh auth status` fails:
  - Authenticate: `gh auth login -h github.com --device`
  - Refresh scopes: `gh auth refresh -h github.com -s read:project,project`
  - In non-interactive runs, stop and return precise auth remediation commands when device flow cannot be completed.
- `gh repo view` fails with not found:
  - Execute repo bootstrap (Step -0.5) if user intends this local repo to be tracked.
- `gh repo view` fails due API/network:
  - Switch to planning-only mode: produce a command plan and do not attempt mutating GitHub operations.
- `git remote -v` returns no `origin`:
  - Treat repo inference as incomplete and run Step -0.5.

### -0.5) Repo bootstrap (when repo/remote is missing)

Use this when there is no remote or the GitHub repo does not exist:

```bash
gh repo create <owner>/<repo> --private --source=. --remote=origin
git push -u origin HEAD
```

Then verify:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,isPrivate
```

Important:
- Fresh repos can report `defaultBranchRef: null` until first successful push.
- If `defaultBranchRef` remains null, push intended default branch (commonly `main`) and re-check.

### 0) Infer repo and project by default

Apply this policy unless the user explicitly passes `owner/repo` or a project:
- Infer repository from current working directory (`gh` defaults to the cwd repo).
- Infer owner/repo from `gh repo view --json nameWithOwner`.
- Infer project with deterministic fallback:
  1. If exactly one open project exists for owner, use it.
  2. Else if exactly one project title contains repo name, use it.
  3. Else if a project title equals `Roadmap` or `<repo> Roadmap`, use it.
  4. Else if no candidate exists, bootstrap a new project (see Step 3).
  5. Else ask one concise question to disambiguate.

Use these discovery commands:

```bash
gh repo view --json nameWithOwner
gh project list --owner <owner> --limit 100 --format json
```

Decision rule for no remote + no repo + ambiguous owner:
- If owner cannot be inferred from auth context or user/org membership, ask one question: `Which owner should host <repo>?`
- Do not create repository/project resources until owner is explicit.

### 1) Baseline the repository workflow

Run these first:

```bash
gh auth status -h github.com
gh auth refresh -h github.com -s read:project,project
gh repo view --json nameWithOwner,defaultBranchRef,isPrivate
gh label list --limit 200
gh issue list --limit 200
```

Inspect existing project structures before creating anything:

```bash
gh project list --owner "@me" --limit 100
```

When a project exists, inspect it:

```bash
gh project view <project-number> --owner <owner> --format json
gh project field-list <project-number> --owner <owner> --format json
gh project item-list <project-number> --owner <owner> --format json
```

### 2) Convert the implementation plan to a work graph

Map the plan to:
- Milestones: major deliverables and target dates.
- Issues: concrete implementation units with acceptance criteria.
- Labels: stable taxonomy (`area/*`, `type/*`, `priority/*`, `status/*`).
- Estimates: either `Estimate` number field in Projects or label-based sizing if no project.
- Dependencies: use sub-issues and linked issues where useful.

Create missing labels idempotently (create if missing, edit if existing):

```bash
gh label create "type/feature" --color 0E8A16 --description "New capability"
gh label create "priority/p1" --color B60205 --description "High priority"
```

Create a milestone via API (no first-class `gh milestone` command):

```bash
gh api repos/<owner>/<repo>/milestones \
  -f title="Phase 1" \
  -f due_on="2026-04-15T23:59:59Z" \
  -f description="Core foundations"
```

Create an issue directly in project flow:

```bash
gh issue create \
  --title "Implement route-level caching for search" \
  --body "<acceptance criteria and test plan>" \
  --label "type/feature" \
  --label "priority/p1" \
  --milestone "Phase 1" \
  --project "Roadmap"
```

### 3) Create or align GitHub Project structure

If no suitable project exists, bootstrap one:

```bash
gh project create --owner <owner> --title "<repo> Roadmap"
gh project link <project-number> --owner <owner> --repo <owner>/<repo>
```

Then ensure minimum planning fields exist:

```bash
gh project field-create <project-number> --owner <owner> --name "Estimate" --data-type NUMBER
gh project field-create <project-number> --owner <owner> --name "Priority" --data-type SINGLE_SELECT --single-select-options "P0,P1,P2,P3"
gh project field-create <project-number> --owner <owner> --name "Target Date" --data-type DATE
```

Use built-in fields (`Status`, `Assignees`, `Labels`, `Milestone`, `Repository`, `Reviewers`) whenever possible before adding custom equivalents.
Prefer creating default views in UI after bootstrap:
- `Board` grouped by `Status`
- `Roadmap` by `Target Date` or iteration
- `Table` with `Estimate`, `Priority`, `Milestone`, `Assignees`

### 4) Synchronize issue/PR/project state

Link PRs to issues with closing keywords in PR body (`Fixes #123`) so merge updates issue state.

Add existing issue/PR items to project when needed:

```bash
gh project item-add <project-number> --owner <owner> --url https://github.com/<owner>/<repo>/issues/<n>
gh project item-add <project-number> --owner <owner> --url https://github.com/<owner>/<repo>/pull/<n>
```

Update project field values on items:

```bash
gh project item-edit \
  --id <item-id> \
  --project-id <project-id> \
  --field-id <field-id> \
  --single-select-option-id <option-id>
```

Prefer this synchronization policy:
- New issue: set `Status=Backlog`, set `Estimate`, set milestone if known.
- PR opened: move related item to `In Progress`.
- PR merged and issue closed: move item to `Done`.
- PR changes requested: move to `Blocked` or `Needs Revision`.

### 5) Configure automation in layers

Configure built-in project workflows first in the UI:
- Item added to project
- Item reopened
- Item closed
- Pull request merged
- Pull request changes requested

Use auto-add workflows from linked repositories for predictable intake.

Add GitHub Actions only when needed for advanced rules or cross-repo sync (for example, field updates on `projects_v2_item` events).

### 6) Operate a planning cadence

For each new implementation plan:
- Create or choose a milestone.
- Generate issues with labels and acceptance criteria.
- Add issues to project and set initial field values.
- Confirm each planned issue has owner, estimate, and status.

For weekly sync:
- Reconcile drift between issue/PR/project state.
- Close stale items or re-scope them.
- Refresh roadmap/insight views.

## Exit Criteria

Do not consider the run complete until all applicable checks pass:
- Repo exists on GitHub and local `origin` uses SSH.
- Default branch is initialized (`defaultBranchRef` is not null).
- Project exists and is linked to target repository.
- Required planning fields exist (`Estimate`, `Priority`, `Target Date`).
- Baseline labels are present and synchronized idempotently.
- Plan issues exist with milestone/labels and project membership.

## Guardrails

- Prefer existing labels and milestones before creating new ones.
- Infer repo/project automatically; ask user only on ambiguity.
- Keep label taxonomy stable; avoid synonyms.
- Do not duplicate tracking across too many custom fields.
- Use draft issues for uncertain work; convert to real issues when ready.
- Keep project updates auditable by using CLI commands and PR references.

## References

Read these files as needed:
- [references/github-project-capabilities.md](references/github-project-capabilities.md): feature matrix and limitations.
