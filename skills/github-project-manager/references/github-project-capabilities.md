# GitHub Project Capabilities (2026 snapshot)

This file captures the GitHub-native feature surface relevant to planning and execution workflows.

## Core planning entities

- Issues: track units of work, support assignees, labels, milestones, issue types, sub-issues.
- Pull requests: implement and review work, can be linked to issues and auto-close issues on merge via closing keywords.
- Milestones: group issues/PRs by release or phase, with due dates and progress.
- Labels: lightweight taxonomy for type, area, priority, and workflow state.
- Projects (ProjectV2): cross-repo planning layer with views, fields, workflows, insights, and draft items.

## Project items

- Add issues and pull requests to a project.
- Create draft issues directly in a project for pre-triage planning.
- Archive or delete items from project views.

## Project fields

Built-in fields include:
- Assignees
- Labels
- Milestone
- Repository
- Reviewers
- Status
- Title
- Parent issue / Sub-issues

Custom field types:
- Text
- Number
- Date
- Single select
- Iteration

Common estimate setup:
- Create a custom number field named `Estimate` and store story points/hours.

## Project views

Primary view types:
- Table
- Board
- Roadmap

Roadmap views use date/iteration-aware fields; board views rely on status-style grouping.

## Built-in project automation

Project workflows support automatic updates for:
- Item added to project
- Item reopened
- Item closed
- Pull request merged
- Pull request changes requested

Auto-add workflows can ingest matching items from linked repositories.

Published limits/features to account for:
- A project can have up to 50 fields and 50 views.
- Auto-add workflow limits depend on plan tier:
  - Free: up to 20 auto-add workflows
  - Pro/Team: up to 50 auto-add workflows
  - Enterprise Cloud: up to 150 auto-add workflows

## Insights and reporting

Projects support chart-based insights including:
- Bar
- Column
- Line
- Area
- Stacked area
- Donut

Use insights for workload distribution, throughput, and milestone burndown-style monitoring.

## API and automation surface

- GitHub Projects V2 are managed through GraphQL (`ProjectV2`).
- REST "projects" endpoints are for Projects (classic), which GitHub has deprecated; use GraphQL for V2 project automation.
- GitHub Actions can react to project-related events, including `projects_v2_item` and `projects_v2_status_update`.
- `gh` CLI supports project creation, linking, field management, item add/edit/list/archive, and project templating.

## Practical constraints for skill behavior

- Prefer reusing existing labels/milestones/fields before creating new ones.
- Infer repository from current working directory by default (`gh` repo context).
- Infer project only when selection is unambiguous; otherwise prompt once.
- If no viable project exists, bootstrap a linked `<repo> Roadmap` project.
- `gh repo view` inference requires a valid git remote and reachable GitHub API.
- Newly created repositories can return empty `defaultBranchRef` until first push.
- For non-interactive environments, provide explicit `gh auth` remediation commands when device flow cannot complete.
- If network/API is unavailable, degrade to planning-only output and avoid mutating operations.
- Keep label taxonomy bounded and deterministic.
- Use draft issues for ambiguous work, convert to issues when ready for execution.
- Use PR closing keywords (`Fixes #123`) to reduce manual synchronization.
- When manually linking PRs to issues, GitHub currently allows up to 10 linked issues per PR.
- Use built-in project workflows first; add Actions only for rules that built-ins cannot express.

## Sources

- https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-fields
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/customizing-the-roadmap-layout
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/adding-items-automatically
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/viewing-insights-from-your-project/creating-charts
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#projects_v2_item
- https://docs.github.com/en/rest/projects-classic/projects
- https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue
- https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/about-milestones
- https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/managing-labels
- https://docs.github.com/en/issues/tracking-your-work-with-issues/configuring-issues/managing-issue-types-in-an-organization
- https://cli.github.com/manual/gh_project
