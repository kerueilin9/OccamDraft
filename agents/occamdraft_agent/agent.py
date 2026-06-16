from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from google.adk.agents.llm_agent import Agent

from occamdraft.draft import DraftGenerator, ReviewProcessor, review_needs_revision
from occamdraft.llm import gemini_from_env, load_dotenv
from occamdraft.models import RouteManifest

load_dotenv()
if os.environ.get("GEMINI_API") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API"]
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")


def summarize_run(run_dir: str) -> dict:
    """Summarize an OccamDraft run directory and tell the user what to do next."""
    run = Path(run_dir)
    manifest = _manifest(run)
    drafts = run / "drafts"
    revised = drafts / "revised"
    accepted = drafts / "accepted"
    pending = _review_summary(_first_existing(revised / "review.json", drafts / "review.json"))
    return {
        "status": "success",
        "run_id": manifest.run_id,
        "sut_id": manifest.sut_id,
        "routes": len(manifest.routes),
        "draft_tasks": _task_count(drafts),
        "accepted_tasks": _task_count(accepted),
        "pending_revised_tasks": _task_count(revised),
        "review": pending,
        "review_path": str((revised / "review.json" if (revised / "review.json").exists() else drafts / "review.json").resolve()),
        "accepted_dir": str(accepted.resolve()),
        "revised_dir": str(revised.resolve()),
    }


def generate_drafts(run_dir: str, max_routes: int = 8) -> dict:
    """Generate initial draft tasks and review.json for an explored run."""
    run = Path(run_dir)
    tasks = DraftGenerator(gemini_from_env()).generate(run, max_routes=max_routes)
    return {
        "status": "success",
        "tasks": len(tasks),
        "drafts_dir": str((run / "drafts").resolve()),
        "review_path": str((run / "drafts" / "review.json").resolve()),
        "next_step": "Open review.json, set each type to accept/revise/remove, add feedback for revise, then ask me to apply the review.",
    }


def apply_review(run_dir: str, review_path: str = "") -> dict:
    """Apply a manually edited review.json. Does not edit review.json for the user."""
    run = Path(run_dir)
    review = Path(review_path) if review_path else None
    llm = gemini_from_env() if review_needs_revision(run, review) else None
    result = ReviewProcessor(llm).process(run, review=review)
    root = _workspace_root(review or run / "drafts" / "review.json")
    pending = _task_count(root / "revised")
    return {
        "status": "success",
        "accepted_tasks": result["accepted"],
        "revised_tasks": result["revised"],
        "removed_tasks": result["removed"],
        "accepted_dir": str((root / "accepted").resolve()),
        "revised_dir": str((root / "revised").resolve()),
        "next_review_path": str((root / "revised" / "review.json").resolve()),
        "done": pending == 0,
        "next_step": "No revised tasks remain; accepted/ is the final task set." if pending == 0 else (
            "Open revised/review.json, review only those tasks, then ask me to apply it again."
        ),
    }


def review_status(run_dir: str, review_path: str = "") -> dict:
    """Inspect a review.json file without applying it."""
    run = Path(run_dir)
    review = Path(review_path) if review_path else _first_existing(run / "drafts" / "revised" / "review.json", run / "drafts" / "review.json")
    return {"status": "success", "review_path": str(review.resolve()), **_review_summary(review)}


def _manifest(run: Path) -> RouteManifest:
    return RouteManifest.model_validate_json((run / "route-manifest.json").read_text("utf-8"))


def _task_count(path: Path) -> int:
    return len(list(path.glob("task*.json"))) if path.exists() else 0


def _review_summary(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "items": 0, "types": {}, "blank": 0}
    data = json.loads(path.read_text("utf-8"))
    values = [item.get("type", "").strip() for item in data.get("items", [])]
    return {"exists": True, "items": len(values), "types": dict(Counter(values)), "blank": values.count("")}


def _first_existing(*paths: Path) -> Path:
    return next((path for path in paths if path.exists()), paths[-1])


def _workspace_root(review: Path) -> Path:
    return review.parent.parent if review.parent.name == "revised" else review.parent


root_agent = Agent(
    model=os.environ.get("OCCAMDRAFT_ADK_MODEL", "gemini-flash-latest"),
    name="occamdraft_agent",
    description="Conversational assistant for OccamDraft web test task drafting and review iteration.",
    instruction="""
You are OccamDraft's conversational operator.

Your job is to help the user run the OccamDraft workflow:
1. Inspect an explored run directory.
2. Generate draft tasks and review.json.
3. Tell the user to manually edit review.json by setting type to accept, revise, or remove.
4. After the user says the JSON is edited, apply the review.
5. If revised tasks remain, point the user to revised/review.json and repeat.
6. When no revised tasks remain, tell the user that drafts/accepted is the final usable task set.

Never edit review.json yourself. The user is responsible for writing type and feedback.
Use exactly one tool per user request, then answer from that tool result.
For status/check requests, call summarize_run.
For draft generation requests, call generate_drafts.
For "I edited review.json" or "apply review" requests, call apply_review.
If the user gives a specific review path, pass it to apply_review.
Do not call review/status tools again after apply_review returns.
Keep responses short and actionable.
If a revise decision is present without feedback, explain that feedback is required and do not proceed.
""".strip(),
    tools=[summarize_run, generate_drafts, apply_review],
)
