#!/usr/bin/env python3
"""Structural checks for the importable n8n workflows in ``n8n/workflows/``.

This is not a substitute for importing them into n8n - n8n validates node
parameters against the installed version, and that needs a running instance.
What it does catch is everything that would otherwise be discovered in the
editor by hand:

* malformed JSON, duplicate node ids or names, nodes without a type/version;
* a connection pointing at a node that does not exist, or at an output index
  the source cannot have;
* a workflow with no trigger, or a webhook that should answer with a Respond
  node but has none;
* a Chat Trigger that is not public, has no CORS allow-list, or allows ``*``;
* credentials, API keys or bearer tokens pasted into a node;
* JavaScript in Code nodes that does not parse (checked with ``node --check``
  when Node is available).

Run:  python scripts/check_n8n_workflows.py
Exit code 1 on any failure.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "n8n" / "workflows"

#: Origins the Chat Trigger must allow. Kept in step with
#: scripts/build_n8n_workflows.py and the README.
REQUIRED_ORIGIN = "sauravprivatelimited369-byte.github.io"

SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bBearer\s+(?!\[redacted\]|<)[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password)\b\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def node_outputs(node: dict) -> int:
    """How many main outputs a node may have. Only IF genuinely needs two."""
    if node.get("type") == "n8n-nodes-base.if":
        return 2
    if node.get("type") == "n8n-nodes-base.switch":
        return 4
    return 1


def check_workflow(path: Path, failures: list[str]) -> None:
    label = path.name
    try:
        data = load(path)
    except json.JSONDecodeError as exc:
        failures.append(f"{label}: invalid JSON ({exc})")
        return

    for key in ("name", "nodes", "connections", "active", "settings"):
        if key not in data:
            failures.append(f"{label}: missing top-level key {key!r}")
    if data.get("active") is not False:
        # A workflow that imports as active would start executing (and spending)
        # before the operator has chosen a credential.
        failures.append(f"{label}: must import inactive")

    nodes = data.get("nodes") or []
    names = [node.get("name") for node in nodes]
    ids = [node.get("id") for node in nodes]
    if len(set(names)) != len(names):
        failures.append(f"{label}: duplicate node names")
    if len(set(ids)) != len(ids):
        failures.append(f"{label}: duplicate node ids")
    if any(not name for name in names):
        failures.append(f"{label}: a node has no name")

    types = [node.get("type", "") for node in nodes]
    triggers = [t for t in types if "trigger" in t.lower() or t.endswith("webhook")]
    if not triggers:
        failures.append(f"{label}: no trigger node")

    by_name = {node.get("name"): node for node in nodes}
    for node in nodes:
        if not node.get("type") or "typeVersion" not in node:
            failures.append(f"{label}: {node.get('name')} has no type/typeVersion")
        position = node.get("position")
        if not (isinstance(position, list) and len(position) == 2):
            failures.append(f"{label}: {node.get('name')} has no [x, y] position")
        if not isinstance(node.get("parameters"), dict):
            failures.append(f"{label}: {node.get('name')} has no parameters object")

    for source, outputs in (data.get("connections") or {}).items():
        if source not in by_name:
            failures.append(f"{label}: connection from unknown node {source!r}")
            continue
        for channel, branches in outputs.items():
            if channel not in {"main", "ai_languageModel", "ai_memory", "ai_tool"}:
                failures.append(f"{label}: unexpected connection type {channel!r} on {source}")
                continue
            if not isinstance(branches, list):
                failures.append(f"{label}: {source}.{channel} is not a list")
                continue
            if channel == "main" and len(branches) > node_outputs(by_name[source]):
                failures.append(f"{label}: {source} has {len(branches)} main outputs, "
                                f"more than its node type provides")
            for index, targets in enumerate(branches):
                for target in targets or []:
                    if target.get("node") not in by_name:
                        failures.append(f"{label}: {source} -> unknown node {target.get('node')!r}")
                    if target.get("index") != 0:
                        failures.append(f"{label}: {source} targets input "
                                        f"{target.get('index')} (only input 0 is wired)")

    # Webhooks that answer themselves need a Respond node somewhere.
    respond_nodes = [n for n in nodes if n.get("type") == "n8n-nodes-base.respondToWebhook"]
    for node in nodes:
        if node.get("type") == "n8n-nodes-base.webhook" and node.get("parameters", {}).get("responseMode") == "responseNode":
            if not respond_nodes:
                failures.append(f"{label}: webhook {node.get('name')} uses responseNode without a Respond node")
            if not node.get("webhookId"):
                failures.append(f"{label}: webhook {node.get('name')} has no webhookId")

    # Chat Trigger configuration: public, restricted origins, explicit mode.
    for node in nodes:
        if node.get("type") != "@n8n/n8n-nodes-langchain.chatTrigger":
            continue
        params = node.get("parameters", {})
        if params.get("public") is not True:
            failures.append(f"{label}: Chat Trigger is not public, so EngineVerse cannot reach it")
        if params.get("mode") != "webhook":
            failures.append(f"{label}: Chat Trigger mode must be 'webhook' (Embedded Chat)")
        origins = str(params.get("options", {}).get("allowedOrigins", ""))
        if not origins or origins.strip() == "*":
            failures.append(f"{label}: Chat Trigger must restrict Allowed Origins, not '*'")
        elif REQUIRED_ORIGIN not in origins:
            failures.append(f"{label}: Chat Trigger Allowed Origins omits {REQUIRED_ORIGIN}")

    # No credential material, and every credential slot must look like a slot.
    blob = json.dumps(data)
    for pattern in SECRET_PATTERNS:
        match = pattern.search(blob)
        if match:
            failures.append(f"{label}: looks like a committed secret ({match.group(0)[:12]}…)")
    for node in nodes:
        for slot, credential in (node.get("credentials") or {}).items():
            ident = str(credential.get("id", ""))
            if not ident.startswith("REPLACE_WITH"):
                failures.append(f"{label}: {node.get('name')} credential {slot!r} should be a "
                                f"REPLACE_WITH… placeholder, found {ident[:24]!r}")

    # http:// is only acceptable for a local test endpoint.
    for match in re.finditer(r"http://([^\"'\s/,#]+)", blob):
        host = match.group(1)
        if host not in {"localhost:8000", "127.0.0.1:8000", "localhost:5678", "127.0.0.1:5678"}:
            failures.append(f"{label}: plain-HTTP URL to {host}")


def check_code_nodes(path: Path, failures: list[str]) -> None:
    """Parse each Code node's JavaScript with Node, when it is installed."""
    node_bin = shutil.which("node")
    if not node_bin:
        return
    data = load(path)
    for node in data.get("nodes", []):
        js = node.get("parameters", {}).get("jsCode")
        if not js:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
            handle.write(js)
            temp = Path(handle.name)
        try:
            result = subprocess.run([node_bin, "--check", str(temp)], capture_output=True, text=True)
            if result.returncode != 0:
                detail = (result.stderr or "").strip().splitlines()[-1:] or ["syntax error"]
                failures.append(f"{path.name}: {node.get('name')} JavaScript does not parse: {detail[0]}")
        finally:
            temp.unlink(missing_ok=True)


def main() -> int:
    if not WORKFLOWS.is_dir():
        print(f"no workflows directory at {WORKFLOWS}")
        return 1
    files = sorted(WORKFLOWS.glob("*.json"))
    if not files:
        print("no workflow JSON files found")
        return 1

    failures: list[str] = []
    for path in files:
        check_workflow(path, failures)
        check_code_nodes(path, failures)

    if failures:
        print(f"{len(failures)} problem(s) in {len(files)} workflows:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"n8n workflows: {len(files)} files, structure and embedded JavaScript valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
