import json
import sys
from threading import Lock
from typing import Any

import coordinator_core as core

STATE_LOCK = Lock()


SERVER_INFO = {
    "name": "agent-coordinator",
    "version": "0.2.0",
}


TOOLS = [
    {
        "name": "get_bridge_state",
        "description": "Return the current shared bridge state as JSON text.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "post_bridge_message",
        "description": "Append a coordination message to the shared bridge state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender": {"type": "string"},
                "recipient": {"type": "string"},
                "type": {"type": "string"},
                "content": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["sender", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_agent_inbox",
        "description": "Return unread or all messages addressed to an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "unread_only": {"type": "boolean"},
            },
            "required": ["agent"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ack_bridge_message",
        "description": "Acknowledge that an agent has read a message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "message_id": {"type": "string"},
            },
            "required": ["agent", "message_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_bridge_status",
        "description": "Update the bridge status and optional summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["status"],
            "additionalProperties": False,
        },
    },
    {
        "name": "claim_bridge_task",
        "description": "Claim or create a task in the shared bridge state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "owner": {"type": "string"},
            },
            "required": ["task_id", "owner"],
            "additionalProperties": False,
        },
    },
    {
        "name": "complete_bridge_task",
        "description": "Mark a shared task as done with a short summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "start_discussion_thread",
        "description": "Start a discussion thread and optionally send the prompt to participants.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "created_by": {"type": "string"},
                "participants": {"type": "array", "items": {"type": "string"}},
                "prompt": {"type": "string"},
            },
            "required": ["title", "created_by"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_discussion_conclusion",
        "description": "Add a conclusion to a discussion thread and write it to discussions.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string"},
                "author": {"type": "string"},
                "summary": {"type": "string"},
                "decisions": {"type": "array", "items": {"type": "string"}},
                "next_steps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["author", "summary"],
            "additionalProperties": False,
        },
    },
    {
        "name": "append_handoff_note",
        "description": "Append a human-readable note to handoff.md.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "task": {"type": "string"},
                "note": {"type": "string"},
                "next_step": {"type": "string"},
            },
            "required": ["agent", "note"],
            "additionalProperties": False,
        },
    },
]


def make_text_result(text: str) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": text,
            }
        ]
    }


def handle_get_bridge_state(_: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
    return make_text_result(json.dumps(state, ensure_ascii=False, indent=2))


def handle_post_bridge_message(arguments: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
        message = core.post_message(state, arguments)
        core.write_state(state)
        core.append_event("message", message)
    return make_text_result(json.dumps(message, ensure_ascii=False, indent=2))


def handle_get_agent_inbox(arguments: dict[str, Any]) -> dict[str, Any]:
    agent = str(arguments.get("agent", "")).strip()
    unread_only = bool(arguments.get("unread_only", True))
    if not agent:
        raise ValueError("agent is required")
    with STATE_LOCK:
        messages = core.get_inbox(core.read_state(), agent, unread_only)
    return make_text_result(json.dumps(messages, ensure_ascii=False, indent=2))


def handle_ack_bridge_message(arguments: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
        message = core.ack_message(
            state,
            str(arguments.get("message_id", "")).strip(),
            str(arguments.get("agent", "")).strip(),
        )
        core.write_state(state)
        core.append_event("ack", {"message_id": message["id"], "agent": arguments.get("agent")})
    return make_text_result(json.dumps(message, ensure_ascii=False, indent=2))


def handle_set_bridge_status(arguments: dict[str, Any]) -> dict[str, Any]:
    status = str(arguments.get("status", "")).strip()
    summary = str(arguments.get("summary", "")).strip()
    if not status:
        raise ValueError("status is required")

    with STATE_LOCK:
        state = core.read_state()
        state["status"] = status
        if summary:
            state["summary"] = summary
        core.write_state(state)
        core.append_event("status", {"status": status, "summary": summary})
    return make_text_result(json.dumps({"status": status, "summary": summary}, ensure_ascii=False, indent=2))


def handle_claim_bridge_task(arguments: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
        task = core.claim_task(state, arguments)
        core.write_state(state)
        core.append_event("claim", task)
    return make_text_result(json.dumps(task, ensure_ascii=False, indent=2))


def handle_complete_bridge_task(arguments: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
        task = core.complete_task(state, arguments)
        core.write_state(state)
        core.append_event("complete_task", task)
    return make_text_result(json.dumps(task, ensure_ascii=False, indent=2))


def handle_start_discussion_thread(arguments: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
        thread = core.start_thread(state, arguments)
        core.write_state(state)
        core.append_event("thread", thread)
    return make_text_result(json.dumps(thread, ensure_ascii=False, indent=2))


def handle_add_discussion_conclusion(arguments: dict[str, Any]) -> dict[str, Any]:
    with STATE_LOCK:
        state = core.read_state()
        conclusion = core.add_conclusion(state, arguments)
        core.write_state(state)
        core.append_event("conclusion", conclusion)
    return make_text_result(json.dumps(conclusion, ensure_ascii=False, indent=2))


def handle_append_handoff_note(arguments: dict[str, Any]) -> dict[str, Any]:
    agent = str(arguments.get("agent", "")).strip()
    task = str(arguments.get("task", "")).strip()
    note = str(arguments.get("note", "")).strip()
    next_step = str(arguments.get("next_step", "")).strip()

    if not agent or not note:
        raise ValueError("agent and note are required")

    section = [
        "",
        f"## {core.utc_now()} - {agent}",
        "",
    ]
    if task:
        section.append(f"Task: {task}")
    section.append(f"Note: {note}")
    if next_step:
        section.append(f"Next: {next_step}")
    section.append("")

    with STATE_LOCK:
        core.ensure_files()
        with core.HANDOFF_PATH.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(section))
        core.append_event(
            "handoff_note",
            {
                "agent": agent,
                "task": task,
                "note": note,
                "next_step": next_step,
            },
        )
    return make_text_result("handoff note appended")


TOOL_HANDLERS = {
    "get_bridge_state": handle_get_bridge_state,
    "post_bridge_message": handle_post_bridge_message,
    "get_agent_inbox": handle_get_agent_inbox,
    "ack_bridge_message": handle_ack_bridge_message,
    "set_bridge_status": handle_set_bridge_status,
    "claim_bridge_task": handle_claim_bridge_task,
    "complete_bridge_task": handle_complete_bridge_task,
    "start_discussion_thread": handle_start_discussion_thread,
    "add_discussion_conclusion": handle_add_discussion_conclusion,
    "append_handoff_note": handle_append_handoff_note,
}


def send_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def success_response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": result,
    }


def error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def handle_initialize(message_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    _ = params
    return success_response(
        message_id,
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": SERVER_INFO,
        },
    )


def handle_tools_list(message_id: Any) -> dict[str, Any]:
    return success_response(message_id, {"tools": TOOLS})


def handle_tools_call(message_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return error_response(message_id, -32601, f"unknown tool: {tool_name}")
    try:
        result = handler(arguments)
        return success_response(message_id, result)
    except ValueError as exc:
        return error_response(message_id, -32602, str(exc))
    except Exception as exc:
        return error_response(message_id, -32000, str(exc))


def main() -> None:
    core.ensure_files()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            send_message(error_response(None, -32700, "parse error"))
            continue

        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params", {})

        if method == "initialize":
            send_message(handle_initialize(message_id, params))
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            send_message(handle_tools_list(message_id))
            continue

        if method == "tools/call":
            send_message(handle_tools_call(message_id, params))
            continue

        send_message(error_response(message_id, -32601, f"method not found: {method}"))


if __name__ == "__main__":
    main()
