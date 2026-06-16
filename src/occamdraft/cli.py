import argparse
import asyncio
import json
import secrets
from pathlib import Path

from .browser import CliError, PlaywrightCli
from .config import find_sut, load_config, resolve_profile_secrets
from .draft import DraftGenerator, ReviewProcessor, review_needs_revision
from .explore import Explorer
from .llm import gemini_from_env


def parser():
    root = argparse.ArgumentParser(prog="occamdraft")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate profile.json")
    validate.add_argument("--profiles", type=Path, required=True)
    explore = commands.add_parser("explore", help="explore a SUT")
    explore.add_argument("--profiles", type=Path, required=True)
    explore.add_argument("--sut", required=True)
    explore.add_argument("--profile", action="append", default=[])
    explore.add_argument("--output", type=Path, default=Path("artifacts"))
    explore.add_argument("--run-id")
    draft = commands.add_parser("draft", help="generate draft Gherkin tasks from a run")
    draft.add_argument("run_dir", type=Path)
    draft.add_argument("--output", type=Path)
    draft.add_argument("--model")
    draft.add_argument("--max-routes", type=int, default=8)
    revise = commands.add_parser("revise", help="apply review.json decisions")
    revise.add_argument("run_dir", type=Path)
    revise.add_argument("--review", type=Path)
    revise.add_argument("--model")
    return root


async def _explore(args):
    config = load_config(args.profiles, resolve_env=False)
    sut = find_sut(config, args.sut)
    if not sut:
        raise SystemExit(f"Unknown SUT: {args.sut}")
    profiles = [profile for profile in sut.profiles if not args.profile or profile.profile_id in args.profile]
    if not profiles:
        raise SystemExit("No matching profiles")
    profiles = [resolve_profile_secrets(profile) for profile in profiles]
    run_id = args.run_id or secrets.token_hex(6)
    manifest = await Explorer(PlaywrightCli(config.browser), args.output).explore(run_id, sut, profiles)
    print(json.dumps({
        "run_id": run_id,
        "routes": len(manifest.routes),
        "manifest": str((args.output / run_id / "route-manifest.json").resolve()),
    }, indent=2))


def main():
    args = parser().parse_args()
    try:
        if args.command == "validate":
            config = load_config(args.profiles, resolve_env=False)
            print(f"valid: {len(config.suts)} SUT(s)")
        elif args.command == "explore":
            asyncio.run(_explore(args))
        elif args.command == "draft":
            tasks = DraftGenerator(gemini_from_env(args.model)).generate(
                args.run_dir, output=args.output, max_routes=args.max_routes
            )
            print(json.dumps({
                "tasks": len(tasks),
                "output": str((args.output or args.run_dir / "drafts").resolve()),
            }, indent=2))
        else:
            llm = gemini_from_env(args.model) if review_needs_revision(args.run_dir, args.review) else None
            result = ReviewProcessor(llm).process(args.run_dir, review=args.review)
            review = args.review or args.run_dir / "drafts" / "review.json"
            root = review.parent.parent if review.parent.name == "revised" else review.parent
            print(json.dumps({
                "accepted_tasks": result["accepted"],
                "revised_tasks": result["revised"],
                "removed_tasks": result["removed"],
                "accepted_dir": str((root / "accepted").resolve()),
                "revised_dir": str((root / "revised").resolve()),
            }, indent=2))
    except (CliError, RuntimeError, ValueError) as error:
        raise SystemExit(f"error: {error}") from None


if __name__ == "__main__":
    main()
