import json
import os
import re
from pathlib import Path

from pydantic import SecretStr

from .models import Profile, ProjectConfig

ENV_REF = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")


def _expand(value):
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, str) and (match := ENV_REF.match(value)):
        name = match.group(1)
        if name not in os.environ:
            raise ValueError(f"Missing environment variable: {name}")
        return os.environ[name]
    return value


def load_config(path: Path, *, resolve_env: bool = True) -> ProjectConfig:
    data = json.loads(path.read_text("utf-8"))
    return ProjectConfig.model_validate(_expand(data) if resolve_env else data)


def find_sut(config: ProjectConfig, sut_id: str):
    return next((sut for sut in config.suts if sut.sut_id == sut_id), None)


def resolve_profile_secrets(profile: Profile) -> Profile:
    for field in ("username", "password"):
        secret = getattr(profile.auth, field)
        if not secret:
            continue
        value = secret.get_secret_value()
        if match := ENV_REF.match(value):
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(f"Missing environment variable: {name}")
            setattr(profile.auth, field, SecretStr(os.environ[name]))
    return profile
