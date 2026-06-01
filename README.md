# Agent Coordinator

> Status: under active development.

A tiny local coordinator for multiple coding agents working in the same workspace. It provides a shared JSON state file, append-only event log, local HTTP API, stdio MCP server, per-agent inboxes, task ownership, discussion threads, and durable conclusions.

This repository is a public, privacy-clean version. It does not include runtime state, local event logs, personal paths, private handoffs, or secrets.

## Features

- Local-only HTTP bridge on `127.0.0.1`
- Zero-dependency Python implementation
- Stdio MCP server for clients that support custom MCP tools
- Shared task state and per-agent inboxes
- Human-readable handoff and discussion conclusion files

## Files

- `bridge_server.py` - local HTTP API
- `coordinator_core.py` - state, events, messages, tasks, and discussion logic
- `mcp_server.py` - stdio MCP server exposing coordinator tools
- `examples/state.example.json` - clean example state
- `examples/handoff.example.md` - clean handoff template
- `examples/discussions.example.md` - clean discussion template

## Start HTTP Bridge

```powershell
python .\bridge_server.py
```

Default server:

```text
http://127.0.0.1:8765
```

## Start MCP Server

```powershell
python .\mcp_server.py
```

Suggested MCP server name: `agent-coordinator`.

## HTTP API

- `GET /health`
- `GET /state`
- `GET /inbox?agent=claude-code`
- `POST /message`
- `POST /ack`
- `POST /claim`
- `POST /complete_task`
- `POST /thread`
- `POST /conclusion`
- `POST /status`

## Privacy

Do not commit runtime files such as `state.json`, `events.jsonl`, real `handoff.md`, real `discussions.md`, `.env`, tokens, API keys, local absolute paths, or private project notes.

## License

MIT
