#!/usr/bin/env python3
"""Automated real-browser check of the local web UI (A-040; F006 SC-001/SC-002/SC-006).

Drives a headless Firefox through its built-in Marionette protocol (plain TCP, no driver download)
with a throwaway profile, against a running `serve` on 127.0.0.1:8080. It checks, in a real
browser engine:
- the page loads and every resource comes from the application origin;
- the CSP blocks a remote image;
- axe-core with all rules, including colour contrast;
- keyboard Tab order with a visible focus indicator;
- ask → cited answer → evidence dialog → Escape restores focus;
- no Web Storage or cookies are written, and a reload starts empty.

It cannot replace a human with a screen reader.

    uv run python scripts/browser_check.py --out data/reports/browser-<utc>.json
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
TAB, ESCAPE = "", ""
QUESTION = "What is the recommended way to set up the development environment?"


class Marionette:
    def __init__(self, port: int) -> None:
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=300)
        self._id = 0
        self._read()  # greeting

    def _read(self) -> Any:
        header = b""
        while not header.endswith(b":"):
            header += self._sock.recv(1)
        size = int(header[:-1])
        body = b""
        while len(body) < size:
            body += self._sock.recv(size - len(body))
        return json.loads(body)

    def call(self, name: str, **params: Any) -> Any:
        self._id += 1
        message = json.dumps([0, self._id, name, params]).encode()
        self._sock.sendall(str(len(message)).encode() + b":" + message)
        _, _, error, result = self._read()
        if error:
            raise RuntimeError(f"{name}: {error.get('error')}: {error.get('message')}")
        return result.get("value") if isinstance(result, dict) and "value" in result else result

    def js(self, script: str, *args: Any) -> Any:
        return self.call("WebDriver:ExecuteScript", script=script, args=list(args))

    def find(self, css: str) -> dict[str, str]:
        return self.call("WebDriver:FindElement", using="css selector", value=css)

    def keys(self, *values: str) -> None:
        actions = []
        for value in values:
            actions += [{"type": "keyDown", "value": value}, {"type": "keyUp", "value": value}]
        self.call(
            "WebDriver:PerformActions", actions=[{"type": "key", "id": "kb", "actions": actions}]
        )

    def wait_text(self, text: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.js("return document.body.innerText.includes(arguments[0]);", text):
                return True
            time.sleep(0.5)
        return False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run(base_url: str, firefox: str, profile_parent: Path, shots: Path) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []

    def step(name: str, ok: bool, detail: str) -> None:
        steps.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {detail}")

    profile = Path(tempfile.mkdtemp(prefix="score-browser-", dir=profile_parent))
    port = free_port()
    (profile / "user.js").write_text(
        f'user_pref("marionette.port", {port});\n'
        'user_pref("browser.shell.checkDefaultBrowser", false);\n'
        'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
        'user_pref("toolkit.telemetry.enabled", false);\n'
    )
    proc = subprocess.Popen(  # noqa: S603 — local browser binary, fixed arguments
        [
            firefox,
            "--headless",
            "--new-instance",
            "--no-remote",
            "--profile",
            str(profile),
            "--marionette",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)
        m = Marionette(port)
        m.call("WebDriver:NewSession", capabilities={})
        m.call("WebDriver:SetWindowRect", width=1280, height=900)
        m.call("WebDriver:Navigate", url=base_url + "/")
        step(
            "page loads with the active snapshot",
            m.wait_text("Snapshot:", 30),
            "header shows the snapshot",
        )

        origins = m.js(
            "return performance.getEntriesByType('resource').map(e => new URL(e.name).origin)"
            ".concat([location.origin]);"
        )
        foreign = sorted({o for o in origins if o != base_url})
        step(
            "every resource is same-origin",
            not foreign,
            f"{len(origins)} entries; foreign: {foreign}",
        )

        violated = m.js(
            """
            return new Promise(resolve => {
              let seen = null;
              document.addEventListener('securitypolicyviolation', e => { seen = e.violatedDirective; });
              const img = document.createElement('img');
              img.src = 'https://example.invalid/pixel.png';
              document.body.appendChild(img);
              setTimeout(() => { img.remove(); resolve(seen); }, 1500);
            });
            """
        )
        step("CSP blocks a remote image", bool(violated), f"violated directive: {violated}")

        axe_source = (ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js").read_text()
        result = m.js(
            axe_source + "\n;return axe.run(document, {resultTypes: ['violations']})"
            ".then(r => r.violations.map(v => v.id + ' (' + v.impact + '): ' + v.nodes.length));"
        )
        step("axe-core, all rules incl. colour contrast", not result, f"violations: {result}")

        m.js("document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0);")
        order: list[str] = []
        unfocused: list[str] = []
        for _ in range(12):
            m.keys(TAB)
            info = m.js(
                """
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                const s = getComputedStyle(el);
                const name = el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText)
                  || el.innerText || el.value || el.tagName;
                const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
                return {name: name.trim().slice(0, 40), visible};
                """
            )
            if info is None:
                break
            order.append(info["name"])
            if not info["visible"]:
                unfocused.append(info["name"])
        step("keyboard Tab reaches the controls in order", len(order) >= 6, " → ".join(order))
        step(
            "visible focus indicator on every focused control",
            not unfocused,
            f"without indicator: {unfocused}",
        )

        question = m.find("#question")
        m.call("WebDriver:ElementSendKeys", id=question[ELEMENT], text=QUESTION)
        # The submit button of the question form (a tab is also labelled "Ask").
        ask = m.find("form.ask button[type=submit]")
        m.call("WebDriver:ElementClick", id=ask[ELEMENT])
        answered = m.wait_text("Answered from the cited sources", 240) or m.wait_text(
            "only part of", 1
        )
        step(
            "ask → cited answer",
            answered,
            "answer rendered with citations" if answered else "no answer",
        )
        if answered:
            marker = m.find(".citation-marker")
            m.call("WebDriver:ElementClick", id=marker[ELEMENT])
            dialog = m.js(
                "const d = document.querySelector('[role=dialog]'); return d ? d.innerText.slice(0, 80) : null;"
            )
            step("citation opens the evidence dialog", bool(dialog), f"dialog: {dialog!r}")
            m.keys(ESCAPE)
            restored = m.js(
                "return !document.querySelector('[role=dialog]') && "
                "document.activeElement.classList.contains('citation-marker');"
            )
            step(
                "Escape closes the dialog and restores focus",
                restored,
                "focus back on the citation marker",
            )
            shot = m.call("WebDriver:TakeScreenshot")
            path = shots / f"browser-answer-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.png"
            path.write_bytes(base64.b64decode(shot))
            step("screenshot of the answer", path.is_file(), str(path))

        stored = m.js(
            "return {local: localStorage.length, session: sessionStorage.length, cookie: document.cookie};"
        )
        empty = stored == {"local": 0, "session": 0, "cookie": ""}
        step("no Web Storage or cookies written", empty, json.dumps(stored))
        m.call("WebDriver:Navigate", url=base_url + "/")
        m.wait_text("Snapshot:", 30)
        cleared = not m.js("return document.body.innerText.includes(arguments[0]);", QUESTION)
        step("reload clears the conversation", cleared, "question text absent after reload")
        m.call("WebDriver:DeleteSession")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--firefox", default=shutil.which("firefox") or "firefox")
    parser.add_argument(
        "--profile-parent",
        type=Path,
        default=Path.home() / "snap" / "firefox" / "common",
        help="Where the throwaway profile is created (snap Firefox can only read its own dirs).",
    )
    args = parser.parse_args(argv)
    args.profile_parent.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    steps = run(args.base_url, args.firefox, args.profile_parent, args.out.parent)
    ok = bool(steps) and all(s["ok"] for s in steps)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "browser": "Firefox (headless, Marionette)",
        "status": "pass" if ok else "fail",
        "reason": "all steps passed" if ok else "; ".join(s["name"] for s in steps if not s["ok"]),
        "not_covered": ["screen reader", "human judgement of the visual design"],
        "steps": steps,
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"browser check: {report['status']} — {report['reason']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
