# JevBrain Decision Console V1

A zero-cost, lightweight local dashboard for inspecting JevBrain evaluation decisions, semantic pipeline judgments, and candidate repair lifecycles.

## Execution Modes

### PRIMARY / FULL MODE

```bash
python dashboard/server.py
```

Optional port argument:
```bash
python dashboard/server.py 8080
```

This provides:
- Dashboard static assets
- `/api/result` (reads current repository `result.json`)
- `/api/logs` (reads current `logs/evaluations.jsonl`)
- Live local result/log integration and refresh

### STATIC-ONLY MODE

```bash
python -m http.server 8080 --directory dashboard
```

This may be used only for:
- Bundled fixtures (Sample PASS, REPAIR, HUMAN REVIEW)
- File upload (custom evaluation JSON)
- Pasted JSON

**Notice:** Static-only mode does NOT provide `/api/result` or `/api/logs`.

## Safety & Security Design

- **Local Bind:** Binds strictly to `127.0.0.1` (loopback only) by default, never `0.0.0.0`.
- **Read-Only API:** Only `GET` requests are served; `POST`, `PUT`, `DELETE`, and `PATCH` are rejected with `405 Method Not Allowed`.
- **Restricted Filesystem Exposure:** Fixed repository paths only (`result.json` and `logs/evaluations.jsonl`). The browser cannot supply arbitrary filesystem paths.
- **Zero Shell Execution:** No shell commands, subprocesses, or dynamic evaluation.
- **No Secret Exposure:** Environment variables and `.env` files are never read or served.
- **Safe Error Handling:** Missing or unparseable files return structured JSON errors (`404` or `500`) without stack traces.
