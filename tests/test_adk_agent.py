import json
from pathlib import Path

from agents.occamdraft_agent.agent import apply_review, review_status, root_agent, summarize_run


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_adk_tools_summarize_and_apply_review(tmp_path: Path):
    run = tmp_path / "run"
    write_json(run / "route-manifest.json", {
        "run_id": "run",
        "sut_id": "timeoff",
        "playwright_cli_version": "fake",
        "routes": [],
    })
    task = {
        "sites": ["timeoff"],
        "task_id": "timeoff_draft_001",
        "order": 1,
        "require_login": True,
        "storage_state": ".auth/timeoff_state.json",
        "start_url": "http://localhost:3102/",
        "gherkin": {"feature": "Employees", "scenario": "Add employee", "given": [], "when": [], "then": ["Done"]},
    }
    write_json(run / "drafts" / "task01.json", task)
    write_json(run / "drafts" / "review.json", {
        "version": 1,
        "run_id": "run",
        "sut_id": "timeoff",
        "items": [{
            "task_file": "task01.json",
            "task_id": "timeoff_draft_001",
            "type": "accept",
            "feedback": "",
            "draft": {
                "require_login": True,
                "page_url": "http://localhost:3102/users/add",
                "gherkin": task["gherkin"],
            },
        }],
    })

    summary = summarize_run(str(run))
    status = review_status(str(run))
    result = apply_review(str(run))

    assert root_agent.name == "occamdraft_agent"
    assert summary["routes"] == 0
    assert status["types"] == {"accept": 1}
    assert result["done"] is True
    assert (run / "drafts" / "accepted" / "task01.json").exists()
    assert json.loads((run / "drafts" / "revised" / "review.json").read_text("utf-8"))["items"] == []
