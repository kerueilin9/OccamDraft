from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .browser import CliError, PlaywrightCli
from .models import NavigationStep, Profile, QueueItem, Route, RouteManifest, Sut


class Explorer:
    def __init__(self, browser: PlaywrightCli, output: Path):
        self.browser = browser
        self.output = output

    async def explore(self, run_id: str, sut: Sut, profiles: list[Profile]) -> RouteManifest:
        routes = []
        version = await self.browser.version()
        for profile in profiles:
            routes.extend(await self._profile(run_id, sut, profile))
        manifest = RouteManifest(
            run_id=run_id, sut_id=sut.sut_id, playwright_cli_version=version, routes=routes
        )
        _write_json(self.output / run_id / "route-manifest.json", manifest.model_dump())
        return manifest

    async def _profile(self, run_id: str, sut: Sut, profile: Profile):
        session = _safe_id(f"occamdraft-{run_id}-{sut.sut_id}-{profile.profile_id}")
        root = urljoin(str(sut.base_url), profile.start_routes[0])
        queue = deque([QueueItem(url=root, depth=0)])
        visited, routes = set(), []
        family_counts = Counter()
        try:
            await self._login(session, run_id, sut, profile)
            while queue and len(routes) < sut.exploration.max_pages:
                item = queue.popleft()
                requested = canonicalize(item.url, sut.exploration.include_query_keys)
                if requested in visited or item.depth > sut.exploration.max_depth or not _allowed(requested, sut):
                    continue
                visited.add(requested)
                metadata, snapshot = await self._observe(session, requested, profile)
                final = canonicalize(metadata["url"], sut.exploration.include_query_keys)
                if _expired(final, profile):
                    await self._login(session, run_id, sut, profile, reopen=False)
                    metadata, snapshot = await self._observe(session, requested, profile)
                    final = canonicalize(metadata["url"], sut.exploration.include_query_keys)
                    if _expired(final, profile):
                        raise CliError(f"Session expired for profile {profile.profile_id}")
                if final in visited and final != requested:
                    continue
                visited.add(final)
                family = route_family(final)
                if family_counts[family] >= sut.exploration.max_pages_per_route_family:
                    continue
                family_counts[family] += 1
                path = _finish_path(item.navigation_path, final)
                links = _normalize_links(metadata["links"], sut)
                metadata["url"] = final
                metadata["links"] = links
                metadata["navigation_path"] = [step.model_dump() for step in path]
                evidence_id = _id(run_id, profile.profile_id, final)
                self._write_evidence(run_id, sut, profile, evidence_id, requested, metadata, snapshot)
                routes.append(Route(
                    route_id=_id(profile.profile_id, final), profile_id=profile.profile_id,
                    role=profile.role, authenticated=profile.auth.type != "none",
                    requested_url=requested, final_url=final, canonical_url=final,
                    route_family=family, title=metadata["title"], depth=item.depth,
                    navigation_path=path, evidence_id=evidence_id,
                ))
                for link in links:
                    target = link["href"]
                    if _safe_navigation(target, link["text"], sut) and target not in visited:
                        queue.append(QueueItem(
                            url=target, depth=item.depth + 1,
                            navigation_path=[*path, *_link_steps(link, final, target)],
                        ))
        finally:
            try:
                await self.browser.close(session)
            except CliError:
                pass
        return routes

    async def _login(self, session: str, run_id: str, sut: Sut, profile: Profile, reopen=True):
        auth = profile.auth
        entry = urljoin(str(sut.base_url), auth.login_route or profile.start_routes[0])
        await (self.browser.open(session, entry) if reopen else self.browser.goto(session, entry))
        if auth.type == "none":
            return
        required = (auth.username, auth.password, auth.username_selector, auth.password_selector, auth.submit_selector)
        if any(value is None for value in required):
            raise ValueError(f"Incomplete form auth config: {profile.profile_id}")
        await self.browser.fill_secret(session, auth.username_selector, auth.username.get_secret_value())
        await self.browser.fill_secret(session, auth.password_selector, auth.password.get_secret_value())
        await self.browser.click(session, auth.submit_selector)
        metadata = await self.browser.metadata(session)
        success = auth.success
        if success and success.url_contains and success.url_contains not in metadata["url"]:
            raise CliError(f"Login verification failed: {profile.profile_id}")
        if success and success.url_not_contains and success.url_not_contains in metadata["url"]:
            raise CliError(f"Login verification failed: {profile.profile_id}")
        if success and success.visible_selector and not await self.browser.visible(session, success.visible_selector):
            raise CliError(f"Login verification failed: {profile.profile_id}")
        await self.browser.state_save(session, self.output / run_id / ".auth" / f"{profile.profile_id}.json")

    async def _observe(self, session: str, url: str, profile: Profile):
        await self.browser.goto(session, url)
        secrets = _profile_secrets(profile)
        return (
            _redact(await self.browser.metadata(session), secrets),
            _redact(await self.browser.snapshot(session), secrets),
        )

    def _write_evidence(self, run_id, sut, profile, evidence_id, requested_url, metadata, snapshot):
        folder = self.output / run_id / "evidence" / evidence_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "snapshot.yml").write_text(snapshot, encoding="utf-8")
        _write_json(folder / "metadata.json", {
            "evidence_id": evidence_id, "sut_id": sut.sut_id, "profile_id": profile.profile_id,
            "role": profile.role, "requested_url": requested_url,
            "observed_at": datetime.now(UTC).isoformat(), **metadata,
        })


def canonicalize(url: str, included_keys=()) -> str:
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key in included_keys]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), ""))


def route_family(url: str) -> str:
    return re.sub(r"/(?:\d+|[0-9a-fA-F-]{32,36})(?=/|$)", "/{id}", urlsplit(url).path)


def _normalize_links(links: list[dict], sut: Sut) -> list[dict]:
    selected = {}
    for link in links:
        link = {
            "context": None, "menu_trigger": None, "visible": False, "text": "", **link,
            "href": canonicalize(link["href"], sut.exploration.include_query_keys),
        }
        score = 4 * bool(link["text"]) + 2 * link["visible"] + bool(link["menu_trigger"])
        if link["href"] not in selected or score > selected[link["href"]][0]:
            selected[link["href"]] = (score, link)
    return [item[1] for item in selected.values()]


def _link_steps(link: dict, source_url: str, target_url: str) -> list[NavigationStep]:
    steps = []
    if trigger := link["menu_trigger"]:
        steps.append(NavigationStep(
            target=trigger["target"], target_type=trigger["target_type"],
            context=trigger["context"], instruction=_instruction(trigger["target"], trigger["context"]),
            source_url=source_url, result_url=source_url,
        ))
    steps.append(NavigationStep(
        target=link["text"] or target_url, target_type="link", context=link["context"],
        instruction=_instruction(link["text"] or target_url, link["context"]),
        source_url=source_url, result_url=target_url,
    ))
    return steps


def _instruction(target: str, context: str | None) -> str:
    return f"Click {target}" + (f" in {context}" if context else "")


def _finish_path(path: list[NavigationStep], final_url: str) -> list[NavigationStep]:
    if not path:
        return []
    path = [step.model_copy() for step in path]
    path[-1].result_url = final_url
    return path


def _allowed(url: str, sut: Sut) -> bool:
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    return origin in {str(value).rstrip("/") for value in sut.allowed_origins}


def _safe_navigation(url: str, text: str, sut: Sut) -> bool:
    value = f"{urlsplit(url).path} {text}".lower()
    blocked = ("logout", "signout", "delete", "remove", "revoke", "approve", "reject",
               "reset-password", "download", "backup")
    return _allowed(url, sut) and not any(word in value for word in blocked)


def _expired(url: str, profile: Profile) -> bool:
    return profile.auth.type == "form" and bool(profile.auth.login_route and profile.auth.login_route in url)


def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "-", value)[:80]


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _profile_secrets(profile: Profile) -> tuple[str, ...]:
    return tuple(secret.get_secret_value() for secret in (profile.auth.username, profile.auth.password) if secret)


def _redact(value, secrets: tuple[str, ...]):
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "<redacted>")
    return value
