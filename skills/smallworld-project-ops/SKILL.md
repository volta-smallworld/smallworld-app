---
name: smallworld-project-ops
description: Apply smallworld-app repository project-management conventions and bootstrap or maintain GitHub planning artifacts for this repo. Use when creating implementation plans, turning plans into issues/milestones/projects, enforcing local label and estimate policy, or running weekly project sync for smallworld-app.
---

# Smallworld Project Ops

## Overview

Use this skill for `smallworld-app` specific policy.
Execute GitHub operations with the local `github-project-manager` skill in this repo:
- `skills/github-project-manager/SKILL.md`

Run deterministic local automation first:
- `scripts/project-sync.sh --doctor --plan project-plan.json`

## Quick Usage

Use one of these prompts:
- `Use $smallworld-project-ops to bootstrap planning for this repo.`
- `Use $smallworld-project-ops to turn this plan into issues and milestones.`
- `Use $smallworld-project-ops to run weekly GitHub project reconciliation.`

## Local Defaults

- Infer repo from current directory.
- Prefer project title: `smallworld-app Roadmap`.
- If project does not exist, create and link it.
- Keep labels, milestones, and issues idempotent.
- Cache project field IDs in `.git/project-field-cache.json`.

## Milestone Reuse-First Policy

Do not create a milestone until reuse checks fail.

Reuse order:
1. Exact title match: `YYYY-MM <Theme>`.
2. Same month and normalized theme (case-insensitive, trimmed spaces).
3. Same month with active/open state and compatible theme.
4. Create only if no reusable milestone exists.

Naming:
- Required format: `YYYY-MM <Theme>`
- Example: `2026-03 Terrain Reliability`

## Canonical Label Taxonomy and Colors

Use these labels and color codes exactly.

- `area/api` `1D76DB`
- `area/mcp` `5319E7`
- `area/web` `0969DA`
- `area/infra` `8250DF`
- `area/data` `0E8A16`
- `type/feature` `0E8A16`
- `type/bug` `D73A4A`
- `type/chore` `6F42C1`
- `type/docs` `0075CA`
- `type/research` `A2EEEF`
- `priority/p0` `B60205`
- `priority/p1` `D93F0B`
- `priority/p2` `FBCA04`
- `priority/p3` `0E8A16`
- `status/blocked` `E11D21`
- `status/needs-info` `C2E0C6`

If a label exists with a different color, edit it to match this map.

## Required Issue Templates

Every issue created from this skill must map to one of these templates.

### Epic Template

Title format:
- `[Epic] <Outcome>`

Required sections:
- `## Goal`
- `## Scope`
- `## Non-Goals`
- `## Milestones`
- `## Risks`
- `## Acceptance Criteria`
- `## Dependencies`

### Feature Template

Title format:
- `[Feature] <Capability>`

Required sections:
- `## Problem`
- `## Proposed Solution`
- `## API/UX Impact`
- `## Acceptance Criteria`
- `## Test Plan`
- `## Rollout Plan`

### Bug Template

Title format:
- `[Bug] <Symptom>`

Required sections:
- `## Observed Behavior`
- `## Expected Behavior`
- `## Reproduction Steps`
- `## Root Cause Hypothesis`
- `## Fix Plan`
- `## Verification`

### Docs Template

Title format:
- `[Docs] <Scope>`

Required sections:
- `## Audience`
- `## Gap`
- `## Proposed Update`
- `## Reviewers`
- `## Completion Criteria`

## Estimate Heuristic Defaults

Use Fibonacci scale `1,2,3,5,8` in project `Estimate` field.

Starting heuristic (override when concrete complexity differs):
- `type/docs` -> `1`
- `type/bug` -> `2` for isolated fix, `3` if cross-service impact
- `type/chore` -> `2`
- `type/feature` -> `3` baseline, `5` for cross-service integration, `8` for broad architectural work
- `type/research` -> `2` baseline, `3` if prototype required
- `epic` parent -> no fixed estimate; estimate child issues instead

## Field ID Discovery and Cache

After project selection, discover field IDs and cache them:

```bash
scripts/project-sync.sh --doctor --plan project-plan.json
cat .git/project-field-cache.json | jq '{projectNumber, projectId, fields}'
```

Expected cache keys:
- `fields.status`
- `fields.estimate`
- `fields.priority`
- `fields.targetDate`

If cache is missing or stale, refresh before any project field edits.

## Execution Rules

Follow this order:
1. Run `scripts/project-sync.sh --doctor --plan project-plan.json`.
2. Run preflight and repo/project inference from `github-project-manager`.
3. Apply smallworld defaults from this skill.
4. Run `scripts/project-sync.sh --apply --plan project-plan.json` for idempotent sync.
5. Synchronize issue/PR/project state.
6. Return summary with created/updated resources.

If `$github-project-manager` is not globally installed:
- Use the local file directly: `skills/github-project-manager/SKILL.md`.
- Continue with the same workflow; do not block on global skill installation.

## Post-Run Verification Checklist

Run these commands and confirm outputs:

```bash
# 1) Project exists
jq -r '.projectTitle' project-plan.json

gh project list --owner "$(gh repo view --json nameWithOwner -q '.nameWithOwner' | cut -d/ -f1)" --limit 100 --format json \
  | jq -e --arg title "$(jq -r '.projectTitle' project-plan.json)" '.projects[] | select(.title==$title) | .number'

# 2) Field cache exists with required IDs
jq -e '.fields.status and .fields.estimate and .fields.priority and .fields.targetDate' .git/project-field-cache.json

# 3) Labels are present with canonical colors
jq -r '.labels[] | "\(.name) \(.color)"' project-plan.json | while read -r name color; do
  gh label list --limit 200 --json name,color \
    | jq -e --arg n "$name" --arg c "$color" '.[] | select(.name==$n and .color==$c)'
done

# 4) Milestone exists
MS_TITLE="$(jq -r '.milestone.title' project-plan.json)"
gh api "repos/$(gh repo view --json nameWithOwner -q '.nameWithOwner')/milestones?state=all&per_page=100" \
  | jq -e --arg t "$MS_TITLE" '.[] | select(.title==$t)'

# 5) Plan-key issues exist
jq -r '.issues[].key' project-plan.json | while read -r key; do
  gh issue list --state all --search "\"plan-key: $key\" in:body" --limit 1 --json number \
    | jq -e 'length == 1'
done
```

Expected outcomes:
- Each command exits `0`.
- No duplicate plan-key issues.
- Label color drift is zero.

## Exit Criteria

- Project `smallworld-app Roadmap` exists (or explicitly chosen equivalent).
- Required labels exist and match canonical colors.
- Active plan issues are linked to milestone and project.
- Estimates are populated for active implementation issues.
- Status reflects current PR/issue state.
- `.git/project-field-cache.json` is present and current.
