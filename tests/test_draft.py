import json
from pathlib import Path

from occamdraft.draft import DraftGenerator
from occamdraft.llm import load_dotenv


class FakeLlm:
    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt: str, schema: dict | None = None) -> str:
        self.prompts.append(prompt)
        assert schema
        return json.dumps([{
            "feature": "Employees",
            "scenario": "Add a new employee account",
            "given": ["I am logged in as an administrator"],
            "when": ["Fill in the First Name field with \"Occam\"", "Click Add new employee"],
            "then": ["The employee should be added to the staff list"],
        }])


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_generates_task_files_with_required_shape(tmp_path: Path):
    run = tmp_path / "run"
    write_json(run / "route-manifest.json", {
        "run_id": "run",
        "sut_id": "timeoff",
        "playwright_cli_version": "fake",
        "routes": [
            {
                "route_id": "home",
                "profile_id": "admin",
                "role": "administrator",
                "authenticated": True,
                "requested_url": "http://localhost:3102/",
                "final_url": "http://localhost:3102/calendar",
                "canonical_url": "http://localhost:3102/calendar",
                "route_family": "/calendar",
                "title": "Calendar",
                "depth": 0,
                "navigation_path": [],
                "evidence_id": "home",
                "status": "observed",
            },
            {
                "route_id": "add",
                "profile_id": "admin",
                "role": "administrator",
                "authenticated": True,
                "requested_url": "http://localhost:3102/users/add",
                "final_url": "http://localhost:3102/users/add",
                "canonical_url": "http://localhost:3102/users/add",
                "route_family": "/users/add",
                "title": "New employee",
                "depth": 2,
                "navigation_path": [
                    {
                        "action": "click",
                        "target": "Employees",
                        "target_type": "link",
                        "context": "header",
                        "instruction": "Click Employees in header",
                        "source_url": "http://localhost:3102/calendar",
                        "result_url": "http://localhost:3102/users",
                    }
                ],
                "evidence_id": "add",
                "status": "observed",
            },
        ],
    })
    write_json(run / "evidence" / "home" / "metadata.json", {"actions": [], "headings": [], "forms": []})
    write_json(run / "evidence" / "add" / "metadata.json", {
        "title": "New employee",
        "headings": ["New employee"],
        "actions": ["New absence", "Add new employee"],
        "forms": [{"fields": [{"label": "First Name", "type": "text", "required": True}]}],
        "tables": [],
    })
    (run / "evidence" / "add" / "snapshot.yml").write_text('- heading "New employee"', encoding="utf-8")
    (run / ".auth").mkdir()
    (run / ".auth" / "admin.json").write_text("{}", encoding="utf-8")

    llm = FakeLlm()
    tasks = DraftGenerator(llm).generate(run)

    assert len(tasks) == 1
    assert 'Fill in the From date field with "2026/04/01"' in llm.prompts[0]
    task = json.loads((run / "drafts" / "task01.json").read_text("utf-8"))
    assert task["sites"] == ["timeoff"]
    assert task["task_id"] == "timeoff_draft_001"
    assert task["order"] == 1
    assert task["require_login"] is True
    assert task["storage_state"] == ".auth/timeoff_state.json"
    assert task["start_url"] == "http://localhost:3102/"
    assert task["gherkin"]["when"][0] == "Click Employees in header"
    assert set(task) == {"sites", "task_id", "order", "require_login", "storage_state", "start_url", "gherkin"}
    assert (run / ".auth" / "timeoff_state.json").exists()


def test_load_dotenv_accepts_spaced_assignment(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GEMINI_API", raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API = 'secret'\n", encoding="utf-8")
    load_dotenv(env)
    assert __import__("os").environ["GEMINI_API"] == "secret"
