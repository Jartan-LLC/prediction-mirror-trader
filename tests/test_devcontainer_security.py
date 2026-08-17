"""Regression test for SEC-2026-0055 / SEC-2026-0056.

.devcontainer/ ran unpinned third-party code as root at container build and
create time, into a container holding a host `.ssh` bind mount and a
docker-outside-of-docker socket bind. Each check below reproduces one
location named in the finding and fails against the unpatched tree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEVCONTAINER_DIR = REPO_ROOT / ".devcontainer"


def _devcontainer_json() -> dict:
    raw = (DEVCONTAINER_DIR / "devcontainer.json").read_text()
    # devcontainer.json is JSONC; strip // comments before parsing.
    without_comments = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    return json.loads(without_comments)


def _setup_sh() -> str:
    return (DEVCONTAINER_DIR / "setup.sh").read_text()


def _claude_settings() -> dict:
    return json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())


def test_base_image_is_digest_pinned():
    image = _devcontainer_json()["image"]
    assert "@sha256:" in image, (
        f"base image {image!r} floats on a mutable tag (devcontainer.json:2)"
    )


def test_no_personal_namespace_claude_code_feature():
    features = _devcontainer_json()["features"]
    assert not any("stu-bell" in ref for ref in features), (
        "personal-namespace ghcr.io/stu-bell/devcontainer-features/claude-code "
        "feature runs as root at build (devcontainer.json:8)"
    )


def test_all_features_are_digest_pinned_in_lock():
    features = _devcontainer_json()["features"]
    lock_path = DEVCONTAINER_DIR / "devcontainer-lock.json"
    assert lock_path.exists(), "no devcontainer-lock.json: features resolve to mutable tags"
    locked = json.loads(lock_path.read_text())["features"]
    for ref in features:
        assert ref in locked, f"{ref} has no lock entry, resolves to a mutable tag"
        assert locked[ref]["resolved"].split("@", 1)[1].startswith("sha256:"), (
            f"{ref} lock entry is not digest-pinned"
        )


def test_setup_sh_does_not_curl_pipe_nodesource():
    setup = _setup_sh()
    assert "deb.nodesource.com" not in setup, (
        "setup.sh:7 pipes an unpinned NodeSource installer into sudo bash"
    )


def test_setup_sh_does_not_install_unpinned_marketplace():
    setup = _setup_sh()
    assert "everything-claude-code" not in setup, (
        "setup.sh reinstalls the unpinned everything-claude-code marketplace "
        "(setup.sh:33-34)"
    )


def test_no_host_ssh_bind_mount():
    mounts = _devcontainer_json().get("mounts", [])
    assert not any(".ssh" in mount for mount in mounts), (
        "devcontainer.json mounts the host's entire ~/.ssh directory into the "
        "container; readonly bounds writing the host's private keys, not "
        "reading them (devcontainer.json:4)"
    )


def test_claude_settings_does_not_enable_unpinned_marketplace():
    settings = _claude_settings()
    enabled = settings.get("enabledPlugins", {})
    assert "everything-claude-code@everything-claude-code" not in enabled, (
        ".claude/settings.json enables the unpinned everything-claude-code "
        "marketplace (SEC-2026-0056)"
    )
