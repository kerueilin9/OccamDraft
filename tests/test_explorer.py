import asyncio
import json
from pathlib import Path

from occamdraft.explore import Explorer
from occamdraft.models import BrowserConfig, Sut


def link(href, text, *, visible=True, context="header", menu_trigger=None):
    return {
        "href": href, "text": text, "visible": visible,
        "context": context, "menu_trigger": menu_trigger,
    }


class FakeBrowser:
    config = BrowserConfig()

    def __init__(self, pages):
        self.pages = pages
        self.current = ""

    async def version(self):
        return "fake"

    async def open(self, session, url):
        self.current = url

    async def goto(self, session, url):
        self.current = url

    async def metadata(self, session):
        page = self.pages.get(self.current, {"links": []})
        return {
            "url": page.get("url", self.current), "title": page.get("title", "Page"),
            "headings": [], "links": page["links"], "forms": [], "tables": [], "actions": [],
        }

    async def snapshot(self, session):
        return '- heading "Page"'

    async def close(self, session):
        pass


def sut(auth=None):
    return Sut.model_validate({
        "sut_id": "demo", "site_name": "demo", "base_url": "https://example.com",
        "allowed_origins": ["https://example.com"],
        "profiles": [{
            "profile_id": "admin" if auth else "guest",
            "role": "administrator" if auth else "guest",
            "start_routes": ["/", "/users"],
            "auth": auth or {"type": "none"},
        }],
        "exploration": {"max_depth": 4, "max_pages": 20, "max_pages_per_route_family": 3},
    })


def run(tmp_path, pages, config=None, run_id="run"):
    config = config or sut()
    return asyncio.run(Explorer(FakeBrowser(pages), tmp_path).explore(run_id, config, config.profiles))


def metadata(tmp_path, run_id, route):
    path = tmp_path / run_id / "evidence" / route.evidence_id / "metadata.json"
    return json.loads(path.read_text("utf-8"))


def test_visible_navigation_path_starts_from_home(tmp_path: Path):
    pages = {
        "https://example.com/": {"links": [link("https://example.com/users?department=1", "Employees")]},
        "https://example.com/users": {"links": []},
    }
    manifest = run(tmp_path, pages)
    users = next(route for route in manifest.routes if route.canonical_url.endswith("/users"))
    assert users.depth == 1
    assert [step.model_dump() for step in users.navigation_path] == [{
        "action": "click", "target": "Employees", "target_type": "link", "context": "header",
        "instruction": "Click Employees in header",
        "source_url": "https://example.com/", "result_url": "https://example.com/users",
    }]
    assert metadata(tmp_path, "run", users)["navigation_path"] == [
        step.model_dump() for step in users.navigation_path
    ]
    assert "edges" not in json.loads((tmp_path / "run" / "route-manifest.json").read_text("utf-8"))


def test_redirected_home_is_deduplicated(tmp_path: Path):
    pages = {
        "https://example.com/": {"url": "https://example.com/calendar?department=1", "links": []},
    }
    manifest = run(tmp_path, pages)
    assert len(manifest.routes) == 1
    assert manifest.routes[0].requested_url == "https://example.com/"
    assert manifest.routes[0].canonical_url == "https://example.com/calendar"
    assert manifest.routes[0].navigation_path == []


def test_dropdown_and_nested_paths_are_complete(tmp_path: Path):
    settings = {"target": "Settings", "target_type": "button", "context": "header"}
    pages = {
        "https://example.com/": {"links": [
            link("https://example.com/reports", "Reports", visible=False,
                 context="Settings menu", menu_trigger=settings),
            link("https://example.com/logout", "Logout", visible=False,
                 context="Me menu", menu_trigger={"target": "Me", "target_type": "button", "context": "header"}),
        ]},
        "https://example.com/reports": {"links": [
            link("https://example.com/reports/allowance", "Allowance usage by time", context=None),
        ]},
        "https://example.com/reports/allowance": {"links": []},
    }
    manifest = run(tmp_path, pages)
    reports = next(route for route in manifest.routes if route.canonical_url.endswith("/reports"))
    allowance = next(route for route in manifest.routes if route.canonical_url.endswith("/allowance"))
    assert [(step.target, step.result_url) for step in reports.navigation_path] == [
        ("Settings", "https://example.com/"),
        ("Reports", "https://example.com/reports"),
    ]
    assert [step.target for step in allowance.navigation_path] == [
        "Settings", "Reports", "Allowance usage by time",
    ]
    assert [step.instruction for step in allowance.navigation_path] == [
        "Click Settings in header", "Click Reports in Settings menu", "Click Allowance usage by time",
    ]
    assert not any(route.canonical_url.endswith("/logout") for route in manifest.routes)


class FakeAuthBrowser(FakeBrowser):
    def __init__(self):
        super().__init__({
            "https://example.com/app": {
                "title": "login@example.com secret", "links": [],
            }
        })
        self.filled = []

    async def fill_secret(self, session, target, value):
        self.filled.append((target, value))

    async def click(self, session, target):
        self.current = "https://example.com/app"

    async def visible(self, session, selector):
        return True

    async def state_save(self, session, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    async def snapshot(self, session):
        return '- heading "login@example.com secret"'


def test_login_credentials_are_redacted(tmp_path: Path):
    config = sut({
        "type": "form", "login_route": "/login", "username": "login@example.com",
        "password": "secret", "username_selector": "#user", "password_selector": "#password",
        "submit_selector": "#submit", "success": {"url_not_contains": "/login"},
    })
    config.profiles[0].start_routes = ["/app"]
    manifest = asyncio.run(Explorer(FakeAuthBrowser(), tmp_path).explore("auth", config, config.profiles))
    artifacts = "".join(path.read_text("utf-8") for path in tmp_path.rglob("*") if path.is_file())
    assert manifest.routes[0].authenticated is True
    assert "login@example.com" not in artifacts
    assert "secret" not in artifacts
    assert "<redacted>" in artifacts
