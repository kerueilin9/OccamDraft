# Task Evaluation Checklist

Use this checklist when reviewing OccamDraft output before accepting tasks into
`drafts/accepted/`.

## Review Decision

Choose exactly one decision per draft:

| Type | Use When |
|---|---|
| `accept` | The task is valuable, executable, and clear enough for OccamQA. |
| `revise` | The task is valuable but needs clearer steps, data, or assertions. |
| `remove` | The task is duplicated, unsafe, low-value, or cannot be executed from current evidence. |

## Basic Validity

Accept only if:

- `feature` names the correct product area.
- `scenario` describes one focused behavior.
- `given` contains real preconditions, not hidden actions.
- `when` contains executable UI steps.
- `then` contains observable expected results.
- The task JSON keeps the OccamQA-compatible shape.

Revise if:

- The scenario mixes multiple independent tasks.
- Required test data is missing.
- Steps are too vague, such as `Fill required fields`.
- Then is too generic, such as `The record should be saved`.

Remove if:

- The task is mostly a duplicate of another candidate.
- It asks to perform risky destructive actions without a safe test target.
- It depends on a page or element not present in evidence.
- It requires business state that OccamDraft did not observe.

## Navigation Quality

Accept only if `when` can start from the home page and reach the target page.

Check that navigation steps are concrete:

```text
Click Employees in header
Click Add new employee
Click Add single employee in Add new employee menu
```

Revise if:

- The task jumps directly to a deep page.
- Dropdown/menu steps are missing.
- The route path does not match the target page.

## Input Step Style

Typed field steps should use this pattern:

```text
Fill in the From date field with "2026/04/01"
Fill in the First Name field with "test"
Fill in the Email Address field with "test.user@example.com"
```

Revise if:

- Values are missing.
- Field names do not match visible labels.
- Date format is inconsistent with the SUT.

## Assertion Quality

Good Then steps should check something visible:

- success message,
- newly added item in a list,
- updated field value,
- removed item no longer appearing,
- table row count or row content,
- page heading or status text.

Revise if Then only says:

```text
The item should be created.
The changes should be saved.
The page should update.
```

Better:

```text
The page should display "New user account successfully added".
The new employee "test user" should appear in the staff list.
```

## Evidence Alignment

Accept only if the task can be traced to page evidence:

- `page_url` is the right page.
- `metadata.json` shows relevant forms, actions, or tables.
- `snapshot.yml` shows relevant labels/buttons.
- `navigation_path` explains how to reach the page.

Revise if:

- The LLM invented fields, buttons, or messages.
- The task assumes a hidden success page.
- The task uses business data not present in evidence or feedback.

## Safety

Remove or revise tasks that:

- delete real data,
- approve/reject real requests,
- reset passwords,
- revoke tokens,
- submit irreversible account settings,
- require production-like credentials.

For delete tasks, prefer safe test records created specifically for the experiment.

## Suggested Evaluation Metrics

For each SUT/run, record:

- number of discovered routes,
- number of generated drafts,
- number accepted initially,
- number revised,
- number removed,
- number accepted after revision,
- average revision rounds per accepted task,
- common revision reasons.

Suggested issue labels:

```text
incomplete_steps
missing_test_data
ambiguous_then
unsupported_by_evidence
duplicate_task
unsafe_action
low_value
```

## Final Acceptance Criteria

A final accepted task should be:

- valuable for testing,
- executable from `start_url`,
- specific about test data,
- grounded in observed page evidence,
- clear about expected visible result,
- safe to run in the experiment environment.

