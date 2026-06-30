# TimeOff Demo Trace

This document records the recommended end-to-end demo flow for OccamDraft.
Use it when preparing a paper demo, screenshots, or a repeatable experiment trace.

## Goal

Show that OccamDraft can:

- explore a logged-in Web system,
- collect route and page evidence,
- generate draft JSON-based Gherkin tasks,
- let a human review drafts through `review.json`,
- iteratively revise tasks,
- produce final usable tasks in `drafts/accepted/`,
- operate the workflow through an ADK conversational agent.

## Preconditions

TimeOff is running locally:

```text
http://localhost:3102/
```

`.env` contains:

```text
GEMINI_API=...
TIMEOFF_ADMIN_USERNAME=...
TIMEOFF_ADMIN_PASSWORD=...
```

The profile file exists:

```text
profiles/profile.example.json
```

## 1. Explore

```powershell
occamdraft explore --profiles profiles/profile.example.json --sut timeoff --profile admin --run-id timeoff-demo
```

Expected artifacts:

```text
artifacts/timeoff-demo/
  route-manifest.json
  .auth/admin.json
  .auth/timeoff_state.json
  evidence/<evidence_id>/
    metadata.json
    snapshot.yml
```

Record for paper/demo:

- number of routes in `route-manifest.json`,
- examples of `navigation_path`,
- one `metadata.json`,
- one `snapshot.yml`.

Useful examples to look for:

```text
Click Employees in header
Click Add new employee
Click Add single employee in Add new employee menu
```

```text
Click Settings in header
Click Reports in Settings menu
```

## 2. Generate Drafts

```powershell
occamdraft draft artifacts/timeoff-demo
```

Expected artifacts:

```text
artifacts/timeoff-demo/drafts/
  task01.json
  task02.json
  draft-tasks.json
  review.json
```

Record for paper/demo:

- number of draft tasks,
- examples of create/update/delete scenarios,
- whether `when` starts with navigation steps,
- whether field input steps use:

```text
Fill in the <field label> field with "<value>"
```

## 3. Human Review

Open:

```text
artifacts/timeoff-demo/drafts/review.json
```

For each item, fill:

```json
{
  "type": "accept",
  "feedback": ""
}
```

or:

```json
{
  "type": "revise",
  "feedback": "Make Then check an observable success message or visible list result."
}
```

or:

```json
{
  "type": "remove",
  "feedback": ""
}
```

Review rules:

- Use `accept` only when the task is already usable.
- Use `revise` when the task has value but needs clearer steps, data, or Then.
- Use `remove` when the task is duplicated, unsafe, low-value, or not executable.

## 4. Apply Review

```powershell
occamdraft revise artifacts/timeoff-demo
```

Expected artifacts:

```text
artifacts/timeoff-demo/drafts/
  accepted/
    task*.json
    draft-tasks.json
  revised/
    task*.json
    draft-tasks.json
    review.json
    review-result.json
```

Record for paper/demo:

- accepted task count,
- revised task count,
- removed task count,
- one before/after revised task pair,
- `review-result.json`.

## 5. Continue Iteration

If `drafts/revised/` contains `task*.json`, open:

```text
artifacts/timeoff-demo/drafts/revised/review.json
```

Fill `type` and `feedback` again, then run:

```powershell
occamdraft revise artifacts/timeoff-demo --review artifacts/timeoff-demo/drafts/revised/review.json
```

Repeat until:

```text
artifacts/timeoff-demo/drafts/revised/
```

has no `task*.json`.

Final usable tasks are in:

```text
artifacts/timeoff-demo/drafts/accepted/
```

## 6. ADK Agent Demo

Start:

```powershell
adk run agents/occamdraft_agent
```

Example conversation:

```text
幫我檢查 artifacts/timeoff-demo 的狀態
```

```text
幫我產生 artifacts/timeoff-demo 的 draft
```

After editing `review.json`:

```text
我已經填好 artifacts/timeoff-demo/drafts/review.json，幫我套用 review
```

If revised tasks remain:

```text
我已經填好 artifacts/timeoff-demo/drafts/revised/review.json，幫我繼續套用
```

Demo point:

- The agent orchestrates the workflow.
- The human still owns review decisions.
- The final task set is produced through iterative human feedback.

