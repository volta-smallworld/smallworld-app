---
name: smallworld-project-ops
description: Apply smallworld-app repository project-management conventions and bootstrap or maintain GitHub planning artifacts for this repo. Use when creating implementation plans, turning plans into issues/milestones/projects, enforcing local label and estimate policy, or running weekly project sync for smallworld-app.
---

# Smallworld Project Ops

## Overview

Use this skill for `smallworld-app` specific policy.
Execute GitHub operations with the local `github-project-manager` skill in this repo:
- `skills/github-project-manager/SKILL.md`

## Quick Usage

Use one of these prompts:
- `Use $smallworld-project-ops to bootstrap planning for this repo.`
- `Use $smallworld-project-ops to turn this plan into issues and milestones.`
- `Use $smallworld-project-ops to run weekly GitHub project reconciliation.`

## Local Defaults

- Infer repo from current directory.
- Prefer project title: `smallworld-app Roadmap`.
- If project does not exist, create and link it.
- Keep labels and milestones idempotent.

## Required Taxonomy

Create and maintain these label groups:
- `area/api`, `area/mcp`, `area/web`, `area/infra`, `area/data`
- `type/feature`, `type/bug`, `type/chore`, `type/docs`, `type/research`
- `priority/p0`, `priority/p1`, `priority/p2`, `priority/p3`
- `status/blocked`, `status/needs-info`

Use estimate scale:
- Fibonacci: `1,2,3,5,8`
- Store in project `Estimate` number field.

Use milestone naming:
- `YYYY-MM <theme>`
- Example: `2026-03 Terrain Reliability`

## Execution Rules

Follow this order:
1. Run preflight and repo/project inference from `github-project-manager`.
2. Apply smallworld defaults from this skill.
3. Create or align milestone, labels, issues, and project fields.
4. Synchronize issue/PR/project state.
5. Return summary with created/updated resources.

If `$github-project-manager` is not globally installed:
- Use the local file directly: `skills/github-project-manager/SKILL.md`.
- Continue with the same workflow; do not block on global skill installation.

## Exit Criteria

- Project `smallworld-app Roadmap` exists (or explicitly chosen equivalent).
- Required labels exist and follow taxonomy above.
- Active plan issues are linked to milestone and project.
- Estimates are populated for active implementation issues.
- Status reflects current PR/issue state.
