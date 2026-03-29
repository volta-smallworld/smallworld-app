#!/usr/bin/env bash
set -euo pipefail

MODE="doctor"
PLAN_FILE="project-plan.json"
CACHE_FILE=".git/project-field-cache.json"
OWNER_OVERRIDE=""
REPO_OVERRIDE=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/project-sync.sh [--doctor|--apply] [--plan <path>] [--cache <path>] [--owner <owner>] [--repo <repo>]

Modes:
  --doctor   Read-only checks and planned actions (default)
  --apply    Idempotent create/update of project labels, milestone, and issues
USAGE
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --doctor)
        MODE="doctor"
        ;;
      --apply)
        MODE="apply"
        ;;
      --plan)
        PLAN_FILE="${2:-}"
        shift
        ;;
      --cache)
        CACHE_FILE="${2:-}"
        shift
        ;;
      --owner)
        OWNER_OVERRIDE="${2:-}"
        shift
        ;;
      --repo)
        REPO_OVERRIDE="${2:-}"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "unknown argument: $1"
        ;;
    esac
    shift
  done
}

json_projects_query='if type=="array" then . else (.projects // []) end'

infer_repo() {
  local name_with_owner
  name_with_owner=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
  OWNER="${name_with_owner%%/*}"
  REPO="${name_with_owner##*/}"

  if [ -n "$OWNER_OVERRIDE" ]; then
    OWNER="$OWNER_OVERRIDE"
  fi
  if [ -n "$REPO_OVERRIDE" ]; then
    REPO="$REPO_OVERRIDE"
  fi
}

find_project_number() {
  gh project list --owner "$OWNER" --limit 100 --format json \
    | jq -r --arg title "$PROJECT_TITLE" "$json_projects_query | .[] | select(.title==\$title) | .number" \
    | head -n1
}

ensure_project() {
  PROJECT_NUMBER=$(find_project_number || true)
  if [ -n "${PROJECT_NUMBER:-}" ]; then
    echo "project: found #$PROJECT_NUMBER ($PROJECT_TITLE)"
    return
  fi

  if [ "$MODE" = "doctor" ]; then
    echo "project: missing -> would create '$PROJECT_TITLE'"
    PROJECT_NUMBER=""
    return
  fi

  gh project create --owner "$OWNER" --title "$PROJECT_TITLE" >/dev/null
  PROJECT_NUMBER=$(find_project_number || true)
  [ -n "${PROJECT_NUMBER:-}" ] || die "failed to create/find project: $PROJECT_TITLE"
  gh project link "$PROJECT_NUMBER" --owner "$OWNER" --repo "$OWNER/$REPO" >/dev/null
  echo "project: created #$PROJECT_NUMBER ($PROJECT_TITLE)"
}

cache_fields() {
  [ -n "${PROJECT_NUMBER:-}" ] || return 0

  local project_json
  local fields_json

  project_json=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json)
  fields_json=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --format json)

  mkdir -p "$(dirname "$CACHE_FILE")"
  jq -n \
    --arg owner "$OWNER" \
    --arg repo "$REPO" \
    --argjson project "$project_json" \
    --argjson fields "$fields_json" \
    '{
      owner: $owner,
      repo: $repo,
      projectNumber: ($project.number // null),
      projectId: ($project.id // null),
      fields: {
        status: (($fields.fields // [])[] | select(.name=="Status") | .id),
        estimate: (($fields.fields // [])[] | select(.name=="Estimate") | .id),
        priority: (($fields.fields // [])[] | select(.name=="Priority") | .id),
        targetDate: (($fields.fields // [])[] | select(.name=="Target Date") | .id)
      },
      refreshedAtEpoch: now
    }' > "$CACHE_FILE"

  echo "cache: wrote $CACHE_FILE"
}

ensure_label() {
  local name="$1" color="$2" desc="$3"
  local exists
  exists=$(gh label list --limit 200 --json name -q ".[] | select(.name == \"$name\") | .name" || true)

  if [ "$MODE" = "doctor" ]; then
    if [ -n "$exists" ]; then
      echo "label: ensure edit $name ($color)"
    else
      echo "label: ensure create $name ($color)"
    fi
    return
  fi

  if [ -n "$exists" ]; then
    gh label edit "$name" --color "$color" --description "$desc" >/dev/null
    echo "label: updated $name"
  else
    gh label create "$name" --color "$color" --description "$desc" >/dev/null
    echo "label: created $name"
  fi
}

ensure_milestone() {
  [ -n "$MILESTONE_TITLE" ] || return 0

  local number
  number=$(gh api "repos/$OWNER/$REPO/milestones?state=all&per_page=100" \
    -q ".[] | select(.title==\"$MILESTONE_TITLE\") | .number" | head -n1 || true)

  if [ "$MODE" = "doctor" ]; then
    if [ -n "$number" ]; then
      echo "milestone: reuse $MILESTONE_TITLE (#$number)"
    else
      echo "milestone: would create $MILESTONE_TITLE"
    fi
    return
  fi

  if [ -n "$number" ]; then
    if [ -n "$MILESTONE_DUE_ON" ] || [ -n "$MILESTONE_DESCRIPTION" ]; then
      local -a patch_args
      patch_args=(--method PATCH "repos/$OWNER/$REPO/milestones/$number")
      if [ -n "$MILESTONE_DUE_ON" ]; then
        patch_args+=(-f "due_on=$MILESTONE_DUE_ON")
      fi
      if [ -n "$MILESTONE_DESCRIPTION" ]; then
        patch_args+=(-f "description=$MILESTONE_DESCRIPTION")
      fi
      gh api "${patch_args[@]}" >/dev/null
    fi
    echo "milestone: reused $MILESTONE_TITLE"
  else
    local -a create_args
    create_args=("repos/$OWNER/$REPO/milestones" -f "title=$MILESTONE_TITLE")
    if [ -n "$MILESTONE_DUE_ON" ]; then
      create_args+=(-f "due_on=$MILESTONE_DUE_ON")
    fi
    if [ -n "$MILESTONE_DESCRIPTION" ]; then
      create_args+=(-f "description=$MILESTONE_DESCRIPTION")
    fi
    gh api "${create_args[@]}" >/dev/null
    echo "milestone: created $MILESTONE_TITLE"
  fi
}

ensure_issue() {
  local issue_json="$1"
  local key title body
  key=$(echo "$issue_json" | jq -r '.key')
  title=$(echo "$issue_json" | jq -r '.title')
  body=$(echo "$issue_json" | jq -r '.body // ""')

  local body_with_key
  body_with_key="$body"
  body_with_key+=$'\n\n'
  body_with_key+="<!-- plan-key: $key -->"

  local existing
  existing=$(gh issue list --state all --search "\"plan-key: $key\" in:body" --limit 1 --json number -q '.[0].number' || true)

  local -a label_args
  label_args=()
  while IFS= read -r label; do
    [ -n "$label" ] || continue
    label_args+=(--label "$label")
  done < <(echo "$issue_json" | jq -r '.labels[]?')

  if [ "$MODE" = "doctor" ]; then
    if [ -n "$existing" ] && [ "$existing" != "null" ]; then
      echo "issue: ensure update #$existing ($key)"
    else
      echo "issue: ensure create ($key)"
    fi
    return
  fi

  local -a milestone_args
  milestone_args=()
  if [ -n "$MILESTONE_TITLE" ]; then
    milestone_args=(--milestone "$MILESTONE_TITLE")
  fi

  if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    gh issue edit "$existing" --title "$title" --body "$body_with_key" "${milestone_args[@]}" "${label_args[@]}" >/dev/null
    ISSUE_NUMBER="$existing"
    echo "issue: updated #$ISSUE_NUMBER ($key)"
  else
    ISSUE_NUMBER=$(gh issue create --title "$title" --body "$body_with_key" "${milestone_args[@]}" "${label_args[@]}" --json number -q '.number')
    echo "issue: created #$ISSUE_NUMBER ($key)"
  fi

  if [ -n "${PROJECT_NUMBER:-}" ]; then
    local issue_url item_id
    issue_url="https://github.com/$OWNER/$REPO/issues/$ISSUE_NUMBER"
    item_id=$(gh project item-list "$PROJECT_NUMBER" --owner "$OWNER" --format json \
      | jq -r --arg url "$issue_url" '.items[] | select(.content.url==$url) | .id' | head -n1 || true)

    if [ -z "$item_id" ]; then
      gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$issue_url" >/dev/null
      echo "project: added issue #$ISSUE_NUMBER to project #$PROJECT_NUMBER"
    fi
  fi
}

main() {
  parse_args "$@"

  require_cmd jq
  require_cmd gh
  require_cmd git

  [ -f "$PLAN_FILE" ] || die "plan file not found: $PLAN_FILE"

  gh auth status -h github.com >/dev/null
  infer_repo

  PROJECT_TITLE=$(jq -r '.projectTitle' "$PLAN_FILE")
  MILESTONE_TITLE=$(jq -r '.milestone.title // empty' "$PLAN_FILE")
  MILESTONE_DUE_ON=$(jq -r '.milestone.dueOn // empty' "$PLAN_FILE")
  MILESTONE_DESCRIPTION=$(jq -r '.milestone.description // empty' "$PLAN_FILE")

  [ -n "$PROJECT_TITLE" ] || die "projectTitle missing in $PLAN_FILE"

  echo "mode: $MODE"
  echo "repo: $OWNER/$REPO"
  echo "plan: $PLAN_FILE"

  ensure_project
  cache_fields

  while IFS= read -r label_json; do
    [ -n "$label_json" ] || continue
    ensure_label \
      "$(echo "$label_json" | jq -r '.name')" \
      "$(echo "$label_json" | jq -r '.color')" \
      "$(echo "$label_json" | jq -r '.description // ""')"
  done < <(jq -c '.labels[]?' "$PLAN_FILE")

  ensure_milestone

  while IFS= read -r issue_json; do
    [ -n "$issue_json" ] || continue
    ensure_issue "$issue_json"
  done < <(jq -c '.issues[]?' "$PLAN_FILE")

  echo "done: project sync complete"
}

main "$@"
