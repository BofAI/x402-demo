"""Helpers to describe the installed bankofai.x402 package."""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path


def _read_direct_url(dist: metadata.Distribution) -> dict:
    text = dist.read_text("direct_url.json")
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def get_installed_x402_sdk_info() -> dict[str, str]:
    """Return version and source metadata for the installed bankofai.x402 package."""
    dist = metadata.distribution("bankofai.x402")
    info: dict[str, str] = {
        "version": dist.version,
        "location": str(Path(dist.locate_file("")).resolve()),
    }

    direct_url = _read_direct_url(dist)
    if not direct_url:
        return info

    url = direct_url.get("url")
    if isinstance(url, str) and url:
        info["source_url"] = url

    vcs_info = direct_url.get("vcs_info")
    if isinstance(vcs_info, dict):
        requested = vcs_info.get("requested_revision")
        if isinstance(requested, str) and requested:
            info["requested_revision"] = requested
        commit_id = vcs_info.get("commit_id")
        if isinstance(commit_id, str) and commit_id:
            info["commit_id"] = commit_id

    subdirectory = direct_url.get("subdirectory")
    if isinstance(subdirectory, str) and subdirectory:
        info["subdirectory"] = subdirectory

    return info


def format_installed_x402_sdk_info(prefix: str = "bankofai.x402") -> list[str]:
    """Format installed SDK info for startup banners and install output."""
    info = get_installed_x402_sdk_info()
    lines = [
        f"  {prefix}: {info['version']}",
        f"  {prefix} location: {info['location']}",
    ]
    if info.get("requested_revision"):
        lines.append(f"  {prefix} requested revision: {info['requested_revision']}")
    if info.get("commit_id"):
        lines.append(f"  {prefix} commit: {info['commit_id']}")
    if info.get("source_url"):
        lines.append(f"  {prefix} source: {info['source_url']}")
    if info.get("subdirectory"):
        lines.append(f"  {prefix} subdirectory: {info['subdirectory']}")
    return lines
