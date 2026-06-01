import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
EVENTS_PATH = ROOT / "events.jsonl"
HANDOFF_PATH = ROOT / "handoff.md"
DISCUSSIONS_PATH = ROOT / "discussions.md"


DEFAULT_STATE = {
    "version": 2,
    "status": "idle",
    "summary": "Coordinator initialized.",
    "updated_at": None,
    "active_task": None,
    "agents": {
        "codex": {"status": "available", "last_seen": None},
        "claude-code": {"status": "available", "last_seen": None},
    },
    "tasks": [],
    "messages": [],
    "threads": [],
    "conclusions": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_files() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        write_state(DEFAULT_STATE)
    if not EVENTS_PATH.exists():
        EVENTS_PATH.write_text("", encoding="utf-8")
    if not HANDOFF_PATH.exists():
        HANDOFF_PATH.write_text(
            "# Agent Handoff\n\n"
            "Use this file for human-readable coordination between Codex, Claude Code, and you.\n",
            encoding="utf-8",
        )
    if not DISCUSSIONS_PATH.exists():
        DISCUSSIONS_PATH.write_text(
            "# Agent Discussions\n\n"
            "This file summarizes discussion threads and conclusions.\n",
            encoding="utf-8",
        )


def migrate_state(state: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(DEFAULT_STATE)
    migrated.update(state)
    migrated["version"] = max(int(migrated.get("version") or 1), 2)
    migrated.setdefault("agents", deepcopy(DEFAULT_STATE["agents"]))
    migrated.setdefault("tasks", [])
    migrated.setdefault("messages", [])
    migrated.setdefault("threads", [])
    migrated.setdefault("conclusions", [])
    return migrated


def read_state() -> dict[str, Any]:
    ensure_files()
    raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return migrate_state(raw)


def write_state(state: dict[str, Any]) -> None:
    updated = migrate_state(state)
    updated["updated_at"] = utc_now()
    STATE_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")


def append_event(event_type: str, payload: dict[str, Any]) -> None:
    ensure_files()
    event = {
        "timestamp": utc_now(),
        "event_type": event_type,
        "payload": payload,
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def make_id(prefix: str) -> str:
    return f"{prefix}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"


def normalize_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise ValueError("tags must be a list")
    return [str(tag) for tag in tags]


def normalize_message(payload: dict[str, Any]) -> dict[str, Any]:
    sender = str(payload.get("sender", "")).strip()
    recipient = str(payload.get("recipient", "all")).strip() or "all"
    content = str(payload.get("content", "")).strip()
    message_type = str(payload.get("type", "note")).strip() or "note"
    thread_id = str(payload.get("thread_id", "")).strip() or None
    task_id = str(payload.get("task_id", "")).strip() or None

    if not sender:
        raise ValueError("sender is required")
    if not content:
        raise ValueError("content is required")

    return {
        "id": make_id("msg"),
        "sender": sender,
        "recipient": recipient,
        "type": message_type,
        "content": content,
        "tags": normalize_tags(payload.get("tags", [])),
        "thread_id": thread_id,
        "task_id": task_id,
        "status": "unread",
        "acknowledged_by": [],
        "timestamp": utc_now(),
    }


def post_message(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    message = normalize_message(payload)
    state["messages"] = (state.get("messages") or [])[-199:] + [message]
    state["summary"] = f"Last message from {message['sender']} to {message['recipient']}."
    if message.get("thread_id"):
        for thread in state.get("threads") or []:
            if thread.get("id") == message["thread_id"]:
                thread["updated_at"] = message["timestamp"]
                break
    return message


def get_inbox(state: dict[str, Any], agent: str, unread_only: bool = True) -> list[dict[str, Any]]:
    agent = agent.strip()
    messages = []
    for message in state.get("messages") or []:
        is_recipient = message.get("recipient") in {agent, "all"}
        is_sender = message.get("sender") == agent
        already_acked = agent in (message.get("acknowledged_by") or [])
        if is_recipient and not is_sender and (not unread_only or not already_acked):
            messages.append(message)
    return messages


def ack_message(state: dict[str, Any], message_id: str, agent: str) -> dict[str, Any]:
    if not message_id or not agent:
        raise ValueError("message_id and agent are required")
    for message in state.get("messages") or []:
        if message.get("id") == message_id:
            acknowledged_by = message.setdefault("acknowledged_by", [])
            if agent not in acknowledged_by:
                acknowledged_by.append(agent)
            if message.get("recipient") == agent or message.get("recipient") == "all":
                message["status"] = "acked"
            return message
    raise ValueError(f"message not found: {message_id}")


def claim_task(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    task_id = str(payload.get("task_id", "")).strip()
    owner = str(payload.get("owner", "")).strip()
    if not task_id or not owner:
        raise ValueError("task_id and owner are required")

    tasks = state.get("tasks") or []
    matched = None
    for task in tasks:
        if task.get("id") == task_id:
            matched = task
            break
    if matched is None:
        matched = {
            "id": task_id,
            "title": str(payload.get("title", task_id)).strip() or task_id,
            "description": str(payload.get("description", "")).strip(),
            "status": "claimed",
            "created_at": utc_now(),
        }
        tasks.append(matched)

    matched["owner"] = owner
    matched["status"] = str(payload.get("status", "claimed")).strip() or "claimed"
    matched["claimed_at"] = utc_now()
    matched["updated_at"] = utc_now()
    state["tasks"] = tasks
    state["active_task"] = task_id
    state["summary"] = f"Task {task_id} claimed by {owner}."
    return matched


def complete_task(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    task_id = str(payload.get("task_id", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    if not task_id:
        raise ValueError("task_id is required")
    for task in state.get("tasks") or []:
        if task.get("id") == task_id:
            task["status"] = "done"
            task["completed_at"] = utc_now()
            task["summary"] = summary
            task["updated_at"] = utc_now()
            state["summary"] = f"Task {task_id} completed."
            return task
    raise ValueError(f"task not found: {task_id}")


def start_thread(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    created_by = str(payload.get("created_by", "")).strip()
    participants = payload.get("participants", ["codex", "claude-code"])
    prompt = str(payload.get("prompt", "")).strip()
    if not title or not created_by:
        raise ValueError("title and created_by are required")
    if not isinstance(participants, list) or not participants:
        raise ValueError("participants must be a non-empty list")

    now = utc_now()
    thread = {
        "id": make_id("thread"),
        "title": title,
        "created_by": created_by,
        "participants": [str(participant) for participant in participants],
        "status": "open",
        "prompt": prompt,
        "created_at": now,
        "updated_at": now,
        "conclusion_id": None,
    }
    state["threads"] = (state.get("threads") or [])[-49:] + [thread]
    state["summary"] = f"Discussion started: {title}."

    if prompt:
        for participant in thread["participants"]:
            if participant != created_by:
                post_message(
                    state,
                    {
                        "sender": created_by,
                        "recipient": participant,
                        "type": "discussion",
                        "content": prompt,
                        "tags": ["discussion"],
                        "thread_id": thread["id"],
                    },
                )
    return thread


def add_conclusion(state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    thread_id = str(payload.get("thread_id", "")).strip() or None
    author = str(payload.get("author", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    decisions = payload.get("decisions", [])
    next_steps = payload.get("next_steps", [])
    if not author or not summary:
        raise ValueError("author and summary are required")
    if not isinstance(decisions, list) or not isinstance(next_steps, list):
        raise ValueError("decisions and next_steps must be lists")

    conclusion = {
        "id": make_id("conclusion"),
        "thread_id": thread_id,
        "author": author,
        "summary": summary,
        "decisions": [str(item) for item in decisions],
        "next_steps": [str(item) for item in next_steps],
        "timestamp": utc_now(),
    }
    state["conclusions"] = (state.get("conclusions") or [])[-99:] + [conclusion]
    if thread_id:
        for thread in state.get("threads") or []:
            if thread.get("id") == thread_id:
                thread["status"] = "concluded"
                thread["conclusion_id"] = conclusion["id"]
                thread["updated_at"] = conclusion["timestamp"]
                break
    state["summary"] = f"Conclusion added by {author}."
    append_discussion_summary(state, conclusion)
    return conclusion


def append_discussion_summary(state: dict[str, Any], conclusion: dict[str, Any]) -> None:
    ensure_files()
    thread_title = conclusion.get("thread_id") or "General"
    for thread in state.get("threads") or []:
        if thread.get("id") == conclusion.get("thread_id"):
            thread_title = thread.get("title") or thread_title
            break

    lines = [
        "",
        f"## {conclusion['timestamp']} - {thread_title}",
        "",
        f"Author: {conclusion['author']}",
        "",
        f"Summary: {conclusion['summary']}",
        "",
    ]
    if conclusion.get("decisions"):
        lines.append("Decisions:")
        lines.extend(f"- {item}" for item in conclusion["decisions"])
        lines.append("")
    if conclusion.get("next_steps"):
        lines.append("Next steps:")
        lines.extend(f"- {item}" for item in conclusion["next_steps"])
        lines.append("")
    with DISCUSSIONS_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def append_handoff_note(payload: dict[str, Any]) -> None:
    agent = str(payload.get("agent", "")).strip()
    task = str(payload.get("task", "")).strip()
    note = str(payload.get("note", "")).strip()
    next_step = str(payload.get("next_step", "")).strip()
    if not agent or not note:
        raise ValueError("agent and note are required")

    section = ["", f"## {utc_now()} - {agent}", ""]
    if task:
        section.append(f"Task: {task}")
    section.append(f"Note: {note}")
    if next_step:
        section.append(f"Next: {next_step}")
    section.append("")

    ensure_files()
    with HANDOFF_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(section))

