from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from .models import DraftTask, Gherkin, Route, RouteManifest

CRUD_TERMS = ("add", "create", "new", "edit", "update", "save", "delete", "remove", "import")
DRAFTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["feature", "scenario", "given", "when", "then"],
        "properties": {
            "feature": {"type": "string"},
            "scenario": {"type": "string"},
            "given": {"type": "array", "items": {"type": "string"}},
            "when": {"type": "array", "items": {"type": "string"}},
            "then": {"type": "array", "items": {"type": "string"}},
        },
    },
}


class DraftGenerator:
    def __init__(self, llm, *, max_snapshot_chars: int = 8000):
        self.llm = llm
        self.max_snapshot_chars = max_snapshot_chars

    def generate(self, run_dir: Path, *, output: Path | None = None, max_routes: int = 8) -> list[DraftTask]:
        manifest = RouteManifest.model_validate_json((run_dir / "route-manifest.json").read_text("utf-8"))
        output = output or run_dir / "drafts"
        start_url = _start_url(manifest)
        _ensure_storage_state(run_dir, manifest)
        tasks: list[DraftTask] = []
        for route in _candidate_routes(run_dir, manifest)[:max_routes]:
            raw_tasks = _loads_array(self.llm.generate_json(self._prompt(run_dir, manifest, route), schema=DRAFTS_SCHEMA))
            for raw in raw_tasks:
                task = _task(manifest, route, raw, order=len(tasks) + 1, start_url=start_url)
                if task:
                    tasks.append(task)
        _write_tasks(output, tasks)
        return tasks

    def _prompt(self, run_dir: Path, manifest: RouteManifest, route: Route) -> str:
        evidence_dir = run_dir / "evidence" / route.evidence_id
        metadata = json.loads((evidence_dir / "metadata.json").read_text("utf-8"))
        snapshot = (evidence_dir / "snapshot.yml").read_text("utf-8")[:self.max_snapshot_chars]
        payload = {
            "site": manifest.sut_id,
            "route": route.model_dump(),
            "page": {
                "title": metadata.get("title"),
                "headings": metadata.get("headings", []),
                "forms": metadata.get("forms", []),
                "tables": metadata.get("tables", []),
                "actions": _local_actions(metadata.get("actions", [])),
            },
            "snapshot": snapshot,
        }
        return f"""
You generate draft web UI test tasks from page evidence.
Return 0 to 5 tasks for this page, matching the provided response JSON schema.

Focus only on create/add, edit/update, and delete/remove scenarios that are visible in the evidence.
Do not invent hidden pages, fields, buttons, success messages, or business rules.
Use concrete draft test data when visible fields need input.
Start every When with the provided navigation_path instructions before page-specific actions.
Write text/date/number input steps as: Fill in the From date field with "2026/04/01".
Use the same wording pattern for all typed fields: Fill in the <field label> field with "<value>".
If this page has no useful CRUD task, return [].

Field intent: feature is the product area, scenario is one short CRUD scenario, given is preconditions,
when is executable UI steps, and then is observable expected result.

Evidence:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def _candidate_routes(run_dir: Path, manifest: RouteManifest) -> list[Route]:
    scored = []
    for route in manifest.routes:
        metadata = _metadata(run_dir, route)
        score = _crud_score(route, metadata)
        if score:
            scored.append((score, route.depth, route))
    return [route for _, _, route in sorted(scored, key=lambda item: (-item[0], item[1], item[2].canonical_url))]


def _crud_score(route: Route, metadata: dict) -> int:
    path = urlsplit(route.canonical_url).path.lower()
    text = " ".join([
        route.canonical_url,
        route.title,
        *metadata.get("headings", []),
        *_local_actions(metadata.get("actions", [])),
    ]).lower()
    forms = sum(len(form.get("fields", [])) for form in metadata.get("forms", []))
    score = 0
    if re.search(r"/(add|new)(/|$)", path):
        score += 10
    if "add new" in text:
        score += 3
    if re.search(r"/edit(/|$)", path):
        score += 8
    if "save changes" in text:
        score += 3
    if "delete" in text or "remove" in text:
        score += 4
    if any(term in text for term in CRUD_TERMS):
        score += 1
    if forms:
        score += 1
    if "delete company account" in text or "logout" in text:
        score -= 5
    return max(score, 0)


def _task(manifest: RouteManifest, route: Route, raw: dict, *, order: int, start_url: str) -> DraftTask | None:
    try:
        gherkin = Gherkin.model_validate(raw)
    except ValidationError:
        return None
    if not (gherkin.scenario and gherkin.when and gherkin.then):
        return None
    path = [step.instruction for step in route.navigation_path]
    gherkin.when = _dedupe([*path, *gherkin.when])
    return DraftTask(
        sites=[manifest.sut_id],
        task_id=f"{manifest.sut_id}_draft_{order:03d}",
        order=order,
        require_login=route.authenticated,
        storage_state=_storage_state(manifest.sut_id) if route.authenticated else "",
        start_url=start_url,
        gherkin=gherkin,
    )


def _loads_array(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("tasks", [])
    if not isinstance(data, list):
        raise ValueError("LLM response must be a JSON array")
    return data


def _write_tasks(output: Path, tasks: list[DraftTask]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for path in output.glob("task*.json"):
        path.unlink()
    for task in tasks:
        path = output / f"task{task.order:02d}.json"
        path.write_text(json.dumps(task.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "draft-tasks.json").write_text(
        json.dumps([task.model_dump() for task in tasks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _metadata(run_dir: Path, route: Route) -> dict:
    path = run_dir / "evidence" / route.evidence_id / "metadata.json"
    return json.loads(path.read_text("utf-8"))


def _local_actions(actions: list[str]) -> list[str]:
    return [action.strip() for action in actions if action.strip() and action.strip().lower() != "new absence"]


def _start_url(manifest: RouteManifest) -> str:
    roots = [route for route in manifest.routes if route.depth == 0]
    return (roots[0].requested_url if roots else manifest.routes[0].requested_url) if manifest.routes else ""


def _storage_state(sut_id: str) -> str:
    return f".auth/{sut_id}_state.json"


def _ensure_storage_state(run_dir: Path, manifest: RouteManifest) -> None:
    route = next((route for route in manifest.routes if route.authenticated), None)
    if not route:
        return
    target = run_dir / _storage_state(manifest.sut_id)
    source = run_dir / ".auth" / f"{route.profile_id}.json"
    if target.exists() or not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def _dedupe(items: list[str]) -> list[str]:
    seen, result = set(), []
    for item in items:
        value = item.strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
