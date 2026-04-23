"""Manifest validation tests for the claude-workflow plugin."""

import json
import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_PATH = PLUGIN_ROOT / ".claude-plugin" / "marketplace.json"

REQUIRED_MANIFEST_FIELDS = ["name", "version", "description", "author"]
SEMVER_RE = r"^\d+\.\d+\.\d+$"
PLUGIN_NAME = "claude-workflow"


def _load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _load_marketplace() -> dict:
    with MARKETPLACE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_plugin_manifest_file_exists():
    assert MANIFEST_PATH.is_file(), f"plugin.json not found at {MANIFEST_PATH}"


def test_plugin_manifest_is_valid_json():
    _load_manifest()


def test_plugin_manifest_has_required_fields():
    data = _load_manifest()
    for field in REQUIRED_MANIFEST_FIELDS:
        assert field in data, f"required field missing: {field}"
    assert isinstance(data["author"], dict), "author must be an object"
    assert "name" in data["author"], "author.name is required"


def test_plugin_manifest_version_is_semver():
    data = _load_manifest()
    version = data["version"]
    assert re.match(SEMVER_RE, version), f"version {version!r} is not semver"


def test_plugin_manifest_name_matches_directory():
    data = _load_manifest()
    assert data["name"] == PLUGIN_NAME, (
        f"plugin name {data['name']!r} does not match expected {PLUGIN_NAME!r}"
    )


def test_marketplace_file_exists():
    assert MARKETPLACE_PATH.is_file(), f"marketplace.json not found at {MARKETPLACE_PATH}"


def test_marketplace_is_valid_json():
    _load_marketplace()


def test_marketplace_references_plugin_name():
    data = _load_marketplace()
    plugins = data.get("plugins")
    assert isinstance(plugins, list), "marketplace.plugins must be a list"
    assert len(plugins) == 1, f"expected exactly one plugin, got {len(plugins)}"
    assert plugins[0]["name"] == PLUGIN_NAME, (
        f"plugin entry name {plugins[0]['name']!r} != {PLUGIN_NAME!r}"
    )
