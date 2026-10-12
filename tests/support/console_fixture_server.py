# ruff: noqa: E501
"""Start the real console on a fixture store, for the console's browser tests (web/e2e/console/*.spec.ts).

Usage (the Playwright `webServer` command of web/playwright.console.config.ts):
    uv run --extra api python tests/support/console_fixture_server.py

Environment: CONSOLE_E2E_PORT (default 4180; must be 1024..65535). The script builds a throw-away repository and store (the same
fixtures as tests/support/console_world.py: recipes a2-haulage, bench-one and two invalid ones; the run 20261007T120000Z-pub-case
with artefacts a2-clip (video/mp4, 300,000 bytes) and a2-notes; a second valid run; a run with a damaged manifest; one queued job),
adds MARKUP to the strings a browser UI renders (recipe description, manifest notes, a stage parameter, the log tail of a failed
stage: `<img src=x onerror=window.__pwned=1>` and friends), copies the console UI build `web/build/console/` into the throw-away
repository, starts `python -m pitstudio_api` on 127.0.0.1:<port>, prints `READY http://127.0.0.1:<port>/ui/` and serves until
terminated; the temporary folders are removed on exit. It needs `pnpm build:console` to have run (otherwise it exits 2).
It writes only under the system temporary folder (or PITSTUDIO_TEST_TMP).
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE.parents[1] / "api"))

import console_world as cw  # noqa: E402
import pytest  # noqa: E402
import runner_world as rw  # noqa: E402

MARKUP = [
    "<img src=x onerror=window.__pwned=1>",
    "<script>window.__pwned=1</script>",
    '"><svg onload=window.__pwned=1>',
    '<a href="javascript:window.__pwned=1">click</a>',
]


def main() -> int:
    port = int(os.environ.get("CONSOLE_E2E_PORT", "4180"))
    ui = rw.ROOT / "web" / "build" / "console"
    if not (ui / "index.html").is_file():
        print(
            f"console UI build not found in {ui.relative_to(rw.ROOT)}: run `pnpm build:console` first", file=sys.stderr
        )
        return 2
    mp = pytest.MonkeyPatch()
    base = Path(tempfile.mkdtemp(prefix="psc", dir=os.environ.get("PITSTUDIO_TEST_TMP") or None))
    atexit.register(shutil.rmtree, base, ignore_errors=True)
    w = rw.make_world(mp, base, fake_disk=False)
    for doc, folder in cw.good_recipes():
        if doc["id"] == "a2-haulage":
            doc["description"] = MARKUP[0]
        w.write_recipe(doc, folder)
    (w.repo / "studio" / "recipes" / "cases" / "broken-one.yaml").write_text(
        f"id: broken-one\ncase: A2\nseed: {MARKUP[1]!r}\nstages: nope\n", encoding="utf-8"
    )
    seeded = cw.seed_run(w)
    manifest = seeded["manifest"]
    manifest["notes"] = list(MARKUP)
    manifest["stages"][0]["params"] = {**manifest["stages"][0]["params"], "label": MARKUP[2]}
    manifest["stages"][2].update(
        {
            "status": "failed",
            "exit_code": 1,
            "error_class": "unknown",
            "outputs": [],
            "log_tail": "boom " + MARKUP[0] + "\n" + MARKUP[3],
        }
    )
    manifest["stages"][2]["attempts"] = [{"n": 1, "error_class": "unknown", "duration_s": 3.5}]
    (w.store / "runs" / cw.RUN_ID / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copytree(ui, w.repo / "web" / "build" / "console")
    for k, v in w.env_vars().items():
        os.environ[k] = v
    from pitstudio.runner import queue

    queue.enqueue({"recipe": "a2-haulage", "profile": "test-profile"})
    env = {
        **os.environ,
        "PITSTUDIO_CONSOLE_PORT": str(port),
        "PITSTUDIO_CONSOLE_ALLOW_ORIGINS": f"http://127.0.0.1:{port}",
    }
    srv = subprocess.Popen([sys.executable, "-m", "pitstudio_api"], env=env, cwd=str(w.base))
    atexit.register(lambda: srv.poll() is None and srv.kill())

    def stop(*_: object) -> None:
        srv.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    import urllib.request

    for _ in range(300):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                break
        except OSError:
            if srv.poll() is not None:
                print("the console exited during start-up", file=sys.stderr)
                return srv.returncode or 1
            time.sleep(0.2)
    print(f"READY http://127.0.0.1:{port}/ui/", flush=True)
    code = srv.wait()
    mp.undo()
    return 0 if code in (0, -15, 15) else code


if __name__ == "__main__":
    sys.exit(main())
