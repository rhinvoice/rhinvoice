"""A stand-in for Chromium: answers the DevTools commands that LocalChromiumPrinter sends.

Started like Chromium (``--user-data-dir=…`` among the arguments). FAKE_CHROMIUM sets how it
behaves (see ``answer``); every command it receives is appended to FAKE_CHROMIUM_LOG as a
JSON line, a navigation with the content of the page it was sent to.
"""

from __future__ import annotations

import base64
import io
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

from pypdf import PdfWriter
from websockets.sync.server import ServerConnection, serve

MODE = os.environ.get("FAKE_CHROMIUM", "print")
TAB = "tab-session"
A4 = (595, 842)


def pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(*A4)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def log(entry: dict[str, object]) -> None:
    with Path(os.environ["FAKE_CHROMIUM_LOG"]).open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry) + "\n")


def answer(connection: ServerConnection, message: dict[str, object]) -> dict[str, object] | None:
    """Answer one command; send events before or after the reply, as Chromium does."""
    method = message["method"]
    params = cast("dict[str, object]", message["params"])
    reply: dict[str, object] = {"id": message["id"], "result": {}}
    if method == "Target.createTarget":
        # A browser event (no session) arrives in between.
        connection.send(json.dumps({"method": "Target.targetCreated", "params": {}}))
        reply["result"] = {} if MODE == "no-target" else {"targetId": "target-1"}
    elif method == "Target.attachToTarget":
        reply["result"] = {"sessionId": TAB}
    elif method == "Page.enable" and MODE == "garbage":
        connection.send("not json")
    elif method == "Page.enable" and MODE == "not-object":
        connection.send("[]")
    elif method == "Page.enable" and MODE == "early-load":
        # The load event of about:blank; the page itself then never loads.
        connection.send(json.dumps({"method": "Page.loadEventFired", "sessionId": TAB}))
    elif method == "Page.navigate":
        page = Path(unquote(urlparse(str(params["url"])).path)).read_text(encoding="utf-8")
        log({"method": method, "page": page})
        if MODE == "load-error":
            reply["result"] = {"frameId": "frame", "errorText": "net::ERR_FILE_NOT_FOUND"}
        elif MODE == "early-load":
            reply["result"] = {"frameId": "frame"}
        else:
            connection.send(json.dumps({"method": "Page.frameStartedLoading", "sessionId": TAB}))
            connection.send(json.dumps(reply))
            connection.send(json.dumps({"method": "Page.loadEventFired", "sessionId": TAB}))
            return None
    elif method == "Page.printToPDF":
        return print_reply(connection, reply)
    return reply


def print_reply(connection: ServerConnection, reply: dict[str, object]) -> dict[str, object] | None:
    if MODE == "stall":
        return None
    if MODE == "hangup":
        connection.close()
        return None
    if MODE == "error":
        return {"id": reply["id"], "error": {"code": -32000, "message": "Printing failed"}}
    data = {
        "not-base64": "%%%",
        "not-pdf": base64.b64encode(b"<html>").decode(),
        "no-data": None,
    }.get(MODE, base64.b64encode(pdf()).decode())
    reply["result"] = {"data": data}
    return reply


def handle(connection: ServerConnection) -> None:
    for raw in connection:
        message = json.loads(raw)
        log({key: message[key] for key in ("method", "params", "sessionId") if key in message})
        reply = answer(connection, message)
        if reply is not None:
            connection.send(json.dumps(reply))


def main() -> None:
    if MODE == "exit":
        sys.exit(1)
    if MODE == "stubborn":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    profile = Path(next(a for a in sys.argv if a.startswith("--user-data-dir=")).split("=", 1)[1])
    log({"arguments": sys.argv[1:]})
    with serve(handle, "127.0.0.1", 0) as server:
        if MODE != "silent":
            time.sleep(0.1)  # Chromium needs a moment, too: the port file comes later.
            port = server.socket.getsockname()[1]
            (profile / "DevToolsActivePort").write_text(f"{port}\n/devtools/browser/fake\n")
        server.serve_forever()


if __name__ == "__main__":
    main()
