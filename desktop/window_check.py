"""Check in the web view of the program that a click on a document opens that document.

    python desktop/window_check.py <address> <email> <password>

Tests in a browser do not show what the program's window does: Apple's WebKit, unlike WebKit
in Playwright, took the whole table for each row, so that every click opened the last document.
This script looks at the list in the same web view as the program, through pywebview.
"""

# A test script reports its steps on the console; it is no package.
# ruff: noqa: T201, INP001

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import webview

PAGES = ("/invoices", "/quotes")
MIN_ROWS = 2
WAIT_SECONDS = 60

# Synchronous: a script's result does not wait for a promise.
LOG_IN = """
(() => {
  const request = new XMLHttpRequest();
  request.open("POST", "/api/auth/login", false);
  request.setRequestHeader("Content-Type", "application/json");
  request.setRequestHeader("X-Rhinvoice-Client", "window-check");
  request.send(JSON.stringify(%s));
  return request.status;
})()
"""

ROWS = "document.querySelectorAll(\"tbody tr a[href^='/documents/']\").length"

# Cells raised above the link hold the row's own controls. In every other cell, the element a
# click on its middle reaches must be the row's link, not the link of another row.
WRONG_TARGETS = """
(() => {
  const wrong = [];
  for (const row of document.querySelectorAll("tbody tr")) {
    const own = row.querySelector("a[href^='/documents/']");
    if (own === null) continue;
    for (const cell of row.cells) {
      if (cell.getBoundingClientRect().width === 0) continue;
      if (getComputedStyle(cell).position !== "static") continue;
      // In a narrow window the table scrolls sideways, and the box around it clips the rest.
      cell.scrollIntoView({ block: "center", inline: "center" });
      const box = cell.getBoundingClientRect();
      const reached = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      const link = reached === null ? null : reached.closest("a");
      if (link !== own) {
        const target = link === null ? String(reached && reached.tagName) : link.textContent;
        wrong.push(own.textContent + " reaches " + target);
      }
    }
  }
  return wrong;
})()
"""


def evaluate(window: Any, script: str) -> Any:  # noqa: ANN401 - pywebview's window, JSON
    """Return the value of ``script``, None while the page cannot tell.

    Not evaluate_js: it wraps the script in eval, which the program's Content-Security-Policy
    forbids in Apple's WebKit.
    """
    result = window.run_js(f"JSON.stringify({script})")
    if result is None:
        return None
    value = json.loads(result)
    # WebView2 encodes what a script returns once more.
    return json.loads(value) if isinstance(value, str) else value


def wait_for_rows(window: Any) -> int:  # noqa: ANN401 - pywebview's window
    """Wait until the list shows its documents; return how many."""
    deadline = time.monotonic() + WAIT_SECONDS
    rows = 0
    while time.monotonic() < deadline:
        rows = evaluate(window, ROWS) or 0
        if rows >= MIN_ROWS:
            break
        time.sleep(1)
    return rows


def check(window: Any, address: str, email: str, password: str) -> str | None:  # noqa: ANN401
    """Return what is wrong, None if every row leads to its own document."""
    credentials = json.dumps({"email": email, "password": password})
    status = evaluate(window, LOG_IN % credentials)
    if status != 200:  # noqa: PLR2004 - HTTP
        return f"login answered {status}"
    for page in PAGES:
        window.load_url(address + page)
        # The list of the page before stays until the page has changed.
        time.sleep(2)
        rows = wait_for_rows(window)
        if rows < MIN_ROWS:
            return f"{page} shows {rows} documents, the check needs {MIN_ROWS}"
        wrong = evaluate(window, WRONG_TARGETS)
        print(f"{page}: {rows} documents checked", flush=True)
        if wrong:
            return f"{page}: " + "; ".join(wrong)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("address")
    parser.add_argument("email")
    parser.add_argument("password")
    args = parser.parse_args()
    problems: list[str] = []

    def run(window: Any) -> None:  # noqa: ANN401 - pywebview's window
        try:
            if problem := check(window, args.address, args.email, args.password):
                problems.append(problem)
        except Exception as error:  # noqa: BLE001 - reported as the check's failure
            problems.append(repr(error))
        finally:
            window.destroy()

    start = f"{args.address}/login"
    window = webview.create_window("Rhinvoice check", start, width=1200, height=800)
    webview.start(run, window)
    if problems:
        print(f"wrong: {problems[0]}", file=sys.stderr, flush=True)
        raise SystemExit(1)
    print("every row leads to its own document", flush=True)


if __name__ == "__main__":
    main()
