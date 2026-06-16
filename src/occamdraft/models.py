from __future__ import annotations

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr


class BrowserConfig(BaseModel):
    cli_executable: str = "playwright-cli"
    headed: bool = False
    snapshot_depth: int | None = None
    command_timeout_seconds: int = 30


class AuthSuccess(BaseModel):
    url_contains: str | None = None
    url_not_contains: str | None = None
    visible_selector: str | None = None


class AuthConfig(BaseModel):
    type: Literal["none", "form"]
    login_route: str | None = None
    username: SecretStr | None = None
    password: SecretStr | None = None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    success: AuthSuccess | None = None


class Profile(BaseModel):
    profile_id: str
    role: str
    start_routes: list[str] = Field(min_length=1)
    auth: AuthConfig


class ExplorationPolicy(BaseModel):
    max_depth: int = Field(default=4, ge=0)
    max_pages: int = Field(default=100, gt=0)
    max_pages_per_route_family: int = Field(default=3, gt=0)
    include_query_keys: list[str] = []
    destructive_actions: Literal["deny"] = "deny"


class Sut(BaseModel):
    sut_id: str
    site_name: str
    base_url: AnyHttpUrl
    allowed_origins: list[AnyHttpUrl]
    profiles: list[Profile] = Field(min_length=1)
    exploration: ExplorationPolicy = ExplorationPolicy()


class ProjectConfig(BaseModel):
    version: Literal[1]
    browser: BrowserConfig = BrowserConfig()
    suts: list[Sut] = Field(min_length=1)


class CliResult(BaseModel):
    command: str
    stdout: str
    stderr: str
    duration_ms: int


class NavigationStep(BaseModel):
    action: Literal["click"] = "click"
    target: str
    target_type: Literal["link", "button"]
    context: str | None = None
    instruction: str
    source_url: str
    result_url: str


class QueueItem(BaseModel):
    url: str
    depth: int
    navigation_path: list[NavigationStep] = Field(default_factory=list)


class Route(BaseModel):
    route_id: str
    profile_id: str
    role: str
    authenticated: bool
    requested_url: str
    final_url: str
    canonical_url: str
    route_family: str
    title: str
    depth: int
    navigation_path: list[NavigationStep]
    evidence_id: str
    status: Literal["observed"] = "observed"


class RouteManifest(BaseModel):
    run_id: str
    sut_id: str
    playwright_cli_version: str
    routes: list[Route]
