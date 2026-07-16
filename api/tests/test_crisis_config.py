"""Hard Rule N8: placeholder crisis config must refuse to boot."""

import json
from pathlib import Path

import pytest

from palio.config import AppEnv, Settings
from palio.safety import crisis_config
from palio.safety.crisis_config import CrisisConfigError

VALID = {
    "country": "SA",
    "lines": [
        {"name": "Test Line", "number": "+966 11 111 1111", "hours": "24/7", "language": "ar"}
    ],
    "updated_at": "2026-07-01",
    "verified_by": "Operator Name, 2026-07-01",
}


def _settings(tmp_path: Path, env: AppEnv, allow: bool, payload: dict | None) -> Settings:
    if payload is not None:
        (tmp_path / "crisis_resources.sa.json").write_text(json.dumps(payload), encoding="utf-8")
    return Settings(
        app_env=env,
        allow_unverified_crisis_config=allow,
        config_dir=str(tmp_path),
        database_url="postgresql+psycopg://unused/unused",
    )


def test_production_with_placeholder_refuses_boot(tmp_path):
    payload = dict(VALID, verified_by="", lines=[dict(VALID["lines"][0], number="PLACEHOLDER")])
    settings = _settings(tmp_path, AppEnv.production, allow=False, payload=payload)
    with pytest.raises(CrisisConfigError, match="REFUSING TO BOOT"):
        crisis_config.validate_at_boot(settings)


def test_production_ignores_dev_escape_hatch(tmp_path):
    """ALLOW_UNVERIFIED_CRISIS_CONFIG must be refused in production."""
    payload = dict(VALID, verified_by="")
    settings = _settings(tmp_path, AppEnv.production, allow=True, payload=payload)
    with pytest.raises(CrisisConfigError):
        crisis_config.validate_at_boot(settings)


def test_dev_without_flag_refuses_boot(tmp_path):
    payload = dict(VALID, verified_by="")
    settings = _settings(tmp_path, AppEnv.development, allow=False, payload=payload)
    with pytest.raises(CrisisConfigError):
        crisis_config.validate_at_boot(settings)


def test_dev_with_flag_boots_unverified(tmp_path):
    payload = dict(VALID, verified_by="")
    settings = _settings(tmp_path, AppEnv.development, allow=True, payload=payload)
    assert crisis_config.validate_at_boot(settings) is False


def test_valid_config_boots_verified(tmp_path):
    settings = _settings(tmp_path, AppEnv.production, allow=False, payload=VALID)
    assert crisis_config.validate_at_boot(settings) is True


def test_missing_config_dir_refuses_boot(tmp_path):
    settings = _settings(tmp_path, AppEnv.production, allow=False, payload=None)
    with pytest.raises(CrisisConfigError):
        crisis_config.validate_at_boot(settings)


def test_repo_placeholder_file_is_detected():
    """The checked-in config/crisis_resources.sa.json must stay blocking."""
    repo_config = Path(__file__).resolve().parents[2] / "config" / "crisis_resources.sa.json"
    problems = crisis_config._validate_file(repo_config)
    assert problems, "repo crisis config unexpectedly passes validation — N8 gate would be moot"


def test_load_marks_unverified(tmp_path):
    payload = dict(VALID, verified_by="")
    settings = _settings(tmp_path, AppEnv.development, allow=True, payload=payload)
    resources = crisis_config.load("sa", settings)
    assert resources is not None
    assert resources.verified is False
    assert resources.lines[0].number == VALID["lines"][0]["number"]
