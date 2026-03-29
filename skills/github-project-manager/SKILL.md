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

## Run Order

Follow this order for every run:
1. Run local sync script first: `scripts/project-sync.sh --doctor --plan project-plan.json`.
2. Run preflight and repo/project inference.
3. Align labels, milestone, and issues idempotently.
4. Ensure project membership and field values.
5. Run verification checklist and return created/updated resources.

## Shell-Safe Snippets (Bash + Zsh)

Prefer newline-delimited loops (no shell arrays needed):

```bash
# bash
while IFS= read -r label; do
  gh label list --limit 200 --json name -q ".[] | select(.name == \"$label\") | .name"
done <<'LABELS'
type/feature
priority/p1
LABELS
```

```zsh
# zsh
while IFS= read -r label; do
  gh label list --limit 200 --json name -q ".[] | select(.name == \"$label\") | .name"
done <<'LABELS'
type/feature
priority/p1
LABELS
```

If arrays are required, use explicit shell syntax:

```bash
# bash arrays
labels=("type/feature" "priority/p1")
for label in "${labels[@]}"; do
  echo "$label"
done
```

```zsh
# zsh arrays
typeset -a labels
labels=("type/feature" "priority/p1")
for label in $labels; do
  echo "$label"
done
```

## Preflight and Remediation

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
  - Execute repo bootstrap if user intends this local repo to be tracked.
- `gh repo view` fails due API/network:
  - Switch to planning-only mode: produce a command plan and do not attempt mutating GitHub operations.
- `git remote -v` returns no `origin`:
  - Treat repo inference as incomplete and run repo bootstrap.

### Sandbox and Network Escalation

When running in a sandboxed environment:
- If a required `gh` command fails due network/DNS/auth sandboxing, re-run the same command with approval/escalation.
- If writes outside the workspace are required (for example global skill install), request approval before retrying.
- Do not continue with partial mutations after a failed mutating command; rerun the failed step first, then resume.

## Repo Bootstrap (When Remote/Repo Is Missing)

```bash
gh repo create <owner>/<repo> --private --source=. --remote=origin
git push -u origin HEAD
gh repo view --json nameWithOwner,defaultBranchRef,isPrivate
```

Important:
- Fresh repos can report `defaultBranchRef: null` until first successful push.
- If `defaultBranchRef` remains null, push intended default branch (commonly `main`) and re-check.

## Strict Naming Conventions

Use deterministic names to avoid drift:
- Milestones: `YYYY-MM <Theme>` (example: `2026-03 Terrain Reliability`)
- Epic issues: `[Epic] <Outcome>`
- Feature issues: `[Feature] <Capability>`
- Bug issues: `[Bug] <Symptom>`
- Docs issues: `[Docs] <Scope>`
- Every generated issue body should include a stable plan marker:
  - `<!-- plan-key: <stable-key> -->`

## Project Inference and Field ID Cache

Infer repository from current working directory unless the user passes explicit `owner/repo`.

Discover project deterministically:
1. If exactly one open project exists for owner, use it.
2. Else if exactly one project title contains repo name, use it.
3. Else if a project title equals `Roadmap` or `<repo> Roadmap`, use it.
4. Else bootstrap a new project.
5. Else ask one concise question.

Discover and cache field IDs after project selection:

```bash
# cache file location (repo-local)
CACHE_FILE=.git/project-field-cache.json

PROJECT_NUMBER=<project-number>
OWNER=<owner>

PROJECT_JSON=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json)
FIELDS_JSON=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json)

jq -n \
  --arg owner "$OWNER" \
  --argjson project "$PROJECT_JSON" \
  --argjson fields "$FIELDS_JSON" \
  '{
    owner: $owner,
    projectId: $project.id,
    projectNumber: $project.number,
    fields: {
      status: ($fields.fields[] | select(.name=="Status") | .id),
      estimate: ($fields.fields[] | select(.name=="Estimate") | .id),
      priority: ($fields.fields[] | select(.name=="Priority") | .id),
      targetDate: ($fields.fields[] | select(.name=="Target Date") | .id)
    },
    refreshedAt: now
  }' > "$CACHE_FILE"
```

## Idempotent Helpers

Use helper patterns to avoid duplicate resources.

### ensure_label

```bash
ensure_label() {
  local name="$1" color="$2" desc="$3"
  local exists
  exists=$(gh label list --limit 200 --json name -q ".[] | select(.name == \"$name\") | .name")
  if [ -n "$exists" ]; then
    gh label edit "$name" --color "$color" --description "$desc"
  else
    gh label create "$name" --color "$color" --description "$desc"
  fi
}
```

### ensure_milestone

```bash
ensure_milestone() {
  local owner="$1" repo="$2" title="$3" due_on="$4" desc="$5"
  local number
  number=$(gh api "repos/$owner/$repo/milestones?state=all&per_page=100" -q ".[] | select(.title==\"$title\") | .number" | head -n1)
  if [ -n "$number" ]; then
    gh api --method PATCH "repos/$owner/$repo/milestones/$number" -f due_on="$due_on" -f description="$desc" >/dev/null
  else
    gh api "repos/$owner/$repo/milestones" -f title="$title" -f due_on="$due_on" -f description="$desc" >/dev/null
  fi
}
```

### ensure_issue

```bash
ensure_issue() {
  local title="$1" body="$2" milestone="$3"
  shift 3
  local labels=("$@")
  local key
  key=$(printf '%s\n' "$body" | sed -n 's/.*plan-key: \([^ ]*\).*/\1/p' | head -n1)

  local existing
  existing=$(gh issue list --state all --search "\"plan-key: $key\" in:body" --limit 1 --json number -q '.[0].number')

  local label_args=()
  local label
  for label in "${labels[@]}"; do
    label_args+=(--label "$label")
  done

  if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    gh issue edit "$existing" --title "$title" --body "$body" --milestone "$milestone" "${label_args[@]}" >/dev/null
    echo "$existing"
  else
    gh issue create --title "$title" --body "$body" --milestone "$milestone" "${label_args[@]}" --json number -q '.number'
  fi
}
```

## Canonical Item Lookup and Field Update

Find project item by issue number:

```bash
ISSUE_URL="https://github.com/$OWNER/$REPO/issues/$ISSUE_NUMBER"
ITEM_ID=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json \
  | jq -r --arg url "$ISSUE_URL" '.items[] | select(.content.url==$url) | .id' \
  | head -n1)
```

Set field value (example: `Priority` single-select):

```bash
gh project item-edit \
  --id "$ITEM_ID" \
  --project-id "$PROJECT_ID" \
  --field-id "$PRIORITY_FIELD_ID" \
  --single-select-option-id "$P1_OPTION_ID"
```

## Bulk Issue Create From JSON

Use `project-plan.json` to reduce repetitive CLI calls:

```bash
jq -c '.issues[]' project-plan.json | while IFS= read -r issue; do
  key=$(echo "$issue" | jq -r '.key')
  title=$(echo "$issue" | jq -r '.title')
  body=$(echo "$issue" | jq -r '.body')
  milestone=$(echo "$issue" | jq -r '.milestone // empty')

  # append stable marker for idempotent lookup
  body_with_key="$body\n\n<!-- plan-key: $key -->"

  cmd=(gh issue create --title "$title" --body "$body_with_key")
  if [ -n "$milestone" ]; then
    cmd+=(--milestone "$milestone")
  fi

  echo "$issue" | jq -r '.labels[]?' | while IFS= read -r label; do
    cmd+=(--label "$label")
  done

  "${cmd[@]}"
done
```

## Planning Cadence

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
- Project field IDs are cached in `.git/project-field-cache.json`.
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
