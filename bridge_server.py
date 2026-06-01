import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any

import coordinator_core as core

HOST = "127.0.0.1"
PORT = 8765
STATE_LOCK = Lock()


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "AgentBridge/0.1"

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        with STATE_LOCK:
            if self.path == "/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "agent_coordinator",
                        "timestamp": core.utc_now(),
                    },
                )
                return
            if self.path == "/state":
                self._send_json(HTTPStatus.OK, core.read_state())
                return
            if self.path.startswith("/inbox"):
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
                agent = params.get("agent", "")
                unread_only = params.get("unread_only", "true").lower() != "false"
                if not agent:
                    raise ValueError("agent query parameter is required")
                self._send_json(HTTPStatus.OK, {"messages": core.get_inbox(core.read_state(), agent, unread_only)})
                return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_json_body()
            with STATE_LOCK:
                state = core.read_state()

                if self.path == "/message":
                    message = core.post_message(state, payload)
                    core.write_state(state)
                    core.append_event("message", message)
                    self._send_json(HTTPStatus.OK, {"ok": True, "message": message})
                    return

                if self.path == "/claim":
                    task = core.claim_task(state, payload)
                    core.write_state(state)
                    core.append_event("claim", task)
                    self._send_json(HTTPStatus.OK, {"ok": True, "task": task})
                    return

                if self.path == "/complete_task":
                    task = core.complete_task(state, payload)
                    core.write_state(state)
                    core.append_event("complete_task", task)
                    self._send_json(HTTPStatus.OK, {"ok": True, "task": task})
                    return

                if self.path == "/ack":
                    message = core.ack_message(
                        state,
                        str(payload.get("message_id", "")).strip(),
                        str(payload.get("agent", "")).strip(),
                    )
                    core.write_state(state)
                    core.append_event("ack", {"message_id": message["id"], "agent": payload.get("agent")})
                    self._send_json(HTTPStatus.OK, {"ok": True, "message": message})
                    return

                if self.path == "/thread":
                    thread = core.start_thread(state, payload)
                    core.write_state(state)
                    core.append_event("thread", thread)
                    self._send_json(HTTPStatus.OK, {"ok": True, "thread": thread})
                    return

                if self.path == "/conclusion":
                    conclusion = core.add_conclusion(state, payload)
                    core.write_state(state)
                    core.append_event("conclusion", conclusion)
                    self._send_json(HTTPStatus.OK, {"ok": True, "conclusion": conclusion})
                    return

                if self.path == "/status":
                    status = str(payload.get("status", "")).strip()
                    summary = str(payload.get("summary", "")).strip()
                    if not status:
                        raise ValueError("status is required")
                    state["status"] = status
                    if summary:
                        state["summary"] = summary
                    core.write_state(state)
                    core.append_event("status", {"status": status, "summary": summary})
                    self._send_json(HTTPStatus.OK, {"ok": True, "status": status})
                    return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def main() -> None:
    core.ensure_files()
    server = ThreadingHTTPServer((HOST, PORT), BridgeHandler)
    print(f"agent_coordinator listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nagent coordinator stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
