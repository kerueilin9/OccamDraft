from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from .models import BrowserConfig, CliResult

METADATA_EXTRACTOR = r"""() => {
  const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const text = e => (e.innerText || e.textContent || '').trim();
  const clean = e => {
    if (!e) return '';
    const copy = e.cloneNode(true);
    copy.querySelectorAll('.caret,.sr-only').forEach(x => x.remove());
    return text(copy).replace(/\s+/g, ' ');
  };
  const region = e => e.closest('nav') ? 'header' : null;
  const menuName = toggle => {
    const value = clean(toggle) || toggle?.getAttribute('aria-label') ||
      toggle?.getAttribute('title') || toggle?.id?.replace(/[_-]+/g, ' ');
    if (value) return value;
    if (toggle?.querySelector('.fa-gears,.fa-cog')) return 'Settings';
    return 'Menu';
  };
  const label = e => e.labels?.[0]?.innerText?.trim() || e.getAttribute('aria-label') || e.name || e.id || '';
  return {
    url: location.href,
    title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3')].filter(visible).map(text),
    links: [...document.querySelectorAll('a[href]')].map(a => {
      const menu = a.closest('.dropdown-menu,[role="menu"]');
      const toggle = menu?.closest('.dropdown,.btn-group')?.querySelector('[data-toggle="dropdown"],.dropdown-toggle');
      return {
        href: a.href, text: clean(a), visible: visible(a),
        context: menu ? `${menuName(toggle)} menu` : region(a),
        menu_trigger: toggle ? {target: menuName(toggle), target_type: 'button', context: region(toggle)} : null
      };
    }),
    forms: [...document.forms].filter(visible).map(f => ({
      fields: [...f.elements].filter(visible).map(e => ({
        label: label(e), type: e.type || e.tagName.toLowerCase(), required: !!e.required
      }))
    })),
    tables: [...document.querySelectorAll('table')].filter(visible).map(t => ({
      headers: [...t.querySelectorAll('th')].map(text), row_count: t.rows.length
    })),
    actions: [...document.querySelectorAll('button,input[type=submit]')].filter(visible).map(e => text(e) || e.value)
  };
}"""


class CliError(RuntimeError):
    pass


class PlaywrightCli:
    def __init__(self, config: BrowserConfig):
        self.config = config
        self.command_prefix = _resolve_command(config.cli_executable)

    async def run(self, session: str | None, *args: str, raw: bool = False, secrets=()) -> CliResult:
        command = [*self.command_prefix]
        if session:
            command.append(f"-s={session}")
        if raw:
            command.append("--raw")
        command.extend(args)
        started = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), self.config.command_timeout_seconds
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise CliError(f"playwright-cli timed out: {args[0]}")
        stdout_text = _redact(stdout.decode(errors="replace").strip(), secrets)
        stderr_text = stderr.decode(errors="replace").strip()
        if process.returncode:
            safe_error = _redact(stderr_text or stdout_text, secrets)
            raise CliError(f"playwright-cli {args[0]} failed: {safe_error}")
        return CliResult(
            command=args[0],
            stdout=stdout_text,
            stderr=_redact(stderr_text, secrets),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )

    async def version(self) -> str:
        return (await self.run(None, "--version")).stdout

    async def open(self, session: str, url: str):
        args = ["open", url]
        if self.config.headed:
            args.append("--headed")
        return await self.run(session, *args)

    async def goto(self, session: str, url: str):
        return await self.run(session, "goto", url)

    async def fill_secret(self, session: str, target: str, value: str):
        return await self.run(session, "fill", target, value, secrets=(value,))

    async def click(self, session: str, target: str):
        return await self.run(session, "click", target)

    async def metadata(self, session: str) -> dict:
        result = await self.run(session, "eval", METADATA_EXTRACTOR, raw=True)
        if not result.stdout:
            raise CliError("playwright-cli eval returned empty metadata")
        return json.loads(result.stdout)

    async def visible(self, session: str, selector: str) -> bool:
        expression = f"() => !!document.querySelector({json.dumps(selector)})"
        return json.loads((await self.run(session, "eval", expression, raw=True)).stdout)

    async def snapshot(self, session: str) -> str:
        args = ["snapshot"]
        if self.config.snapshot_depth is not None:
            args.append(f"--depth={self.config.snapshot_depth}")
        return (await self.run(session, *args, raw=True)).stdout

    async def state_save(self, session: str, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        return await self.run(session, "state-save", str(path.resolve()))

    async def close(self, session: str):
        return await self.run(session, "close")


def _redact(text: str, secrets) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


def _resolve_command(executable: str) -> list[str]:
    found = shutil.which(executable) or executable
    if os.name == "nt" and Path(found).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        folder = Path(found).parent
        script = folder / "node_modules" / "@playwright" / "cli" / "playwright-cli.js"
        node = folder / "node.exe"
        if script.exists():
            return [str(node if node.exists() else shutil.which("node") or "node"), str(script)]
    return [found]
