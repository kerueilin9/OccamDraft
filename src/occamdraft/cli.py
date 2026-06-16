import argparse
import asyncio
import json
import secrets
from pathlib import Path

from .browser import CliError, PlaywrightCli
from .config import find_sut, load_config, resolve_profile_secrets
from .explore import Explorer


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
        else:
            asyncio.run(_explore(args))
    except (CliError, ValueError) as error:
        raise SystemExit(f"error: {error}") from None


if __name__ == "__main__":
    main()
