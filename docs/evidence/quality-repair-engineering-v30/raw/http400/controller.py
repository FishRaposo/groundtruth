"""Real HTTP equality, SSE, isolation and early-disconnect checks after restart."""
import json
import time
from pathlib import Path

import httpx

q = Path(__file__).resolve().parent
out = q / "typed-restart-http-v400"
assert not out.exists()
out.mkdir()
seed = json.loads((q / "typed-connected-live-v378/private/seed.json").read_text())
assert seed["api_url"] == "http://127.0.0.1:8401"
secrets = [p["api_key"] for p in seed["principals"].values()]


def save(name, value):
    text = json.dumps(value, indent=2) + "\n"
    assert not any(secret in text for secret in secrets)
    with (out / name).open("x", encoding="utf-8") as stream:
        stream.write(text)


counts = {"saved_queries_equal": 0, "saved_sources_equal": 0, "cross_workspace_denials": 0}
with httpx.Client(base_url=seed["api_url"], timeout=300) as client:
    ready = client.get("/api/health/ready")
    ready.raise_for_status()
    save("readiness-after-restart.json", ready.json())
    assert ready.json()["status"] == "ready"
    projects = seed["typed_connected_v360"]["projects"]
    by_viewport = {}
    for width in ("390", "768", "1440"):
        project = projects[width]
        headers = {"X-API-Key": seed["principals"][project["principal_alias"]]["api_key"]}
        records = []
        files = sorted((q / "typed-connected-visual-v388/records-before-restart").glob(width + "-*.json"))
        for file in files:
            old = json.loads(file.read_text())
            if "-source-" in file.name:
                # Snapshot filename records the query and citation index.
                identifier, index = file.stem[len(width) + 1:].split("-source-")
                route = f"/api/queries/{identifier}/sources/{index}"
                bucket = "saved_sources_equal"
            else:
                route = "/api/queries/" + old["id"]
                bucket = "saved_queries_equal"
                records.append(old)
            response = client.get(route, headers=headers)
            response.raise_for_status()
            assert response.json() == old, "Restart changed immutable saved presentation"
            counts[bucket] += 1
        assert len(records) == 4
        by_viewport[width] = (headers, records)
    assert counts["saved_queries_equal"] == 12 and counts["saved_sources_equal"] == 6
    widths = ("390", "768", "1440")
    for index, width in enumerate(widths):
        headers, records = by_viewport[width]
        forbidden = by_viewport[widths[(index + 1) % 3]][1][0]
        response = client.get("/api/queries/" + forbidden["id"], headers=headers)
        assert response.status_code == 404
        counts["cross_workspace_denials"] += 1
    headers, records = by_viewport["390"]
    current = next(r for r in records if r["outcome"] == "completed" and any(s["document_version"] == 2 for s in r["sources"]))
    payload = {"question": current["question"], "retrieval_method": "keyword", "top_k": 5}
    events = []
    with client.stream("POST", "/api/queries/stream", headers=headers, json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert not any(e["type"] == "error" for e in events)
    terminal = [e for e in events if e["type"] == "done"]
    assert len(terminal) == 1
    done = {k: v for k, v in terminal[0].items() if k != "type"}
    assert done["outcome"] == "completed" and done["refused"] is False
    assert done["answer"] == current["answer"]
    assert "".join(e["content"] for e in events if e["type"] == "token") == done["answer"]
    identity = lambda s: (s["document_id"], s["document_version"], s["content_hash"], s["quoted_text"])
    assert list(map(identity, done["sources"])) == list(map(identity, current["sources"]))
    saved = client.get("/api/queries/" + done["id"], headers=headers)
    saved.raise_for_status()
    assert saved.json() == done
    save("sse-events.json", events)
    save("sse-saved.json", done)
    # Close immediately after headers, before asking to consume any body event.
    conversation = client.post("/api/conversations", headers=headers, json={"title": "Disposable early-disconnect verification"})
    conversation.raise_for_status()
    conversation_id = conversation.json()["id"]
    with client.stream("POST", "/api/queries/stream", headers=headers, json={**payload, "conversation_id": conversation_id}) as response:
        response.raise_for_status()
    deadline = time.monotonic() + 30
    cancelled = None
    while time.monotonic() < deadline:
        listing = client.get("/api/queries", headers=headers, params={"conversation_id": conversation_id, "limit": 10})
        listing.raise_for_status()
        items = listing.json()["queries"]
        if items:
            cancelled = client.get("/api/queries/" + items[0]["id"], headers=headers).json()
            if cancelled["outcome"] in ("interrupted", "completed", "error"):
                break
        time.sleep(0.25)
    assert cancelled and cancelled["outcome"] == "interrupted", "Early disconnect must not publish a completed answer"
    assert cancelled["answer"] is None and cancelled["sources"] == []
    save("early-disconnect.json", cancelled)
save("result.json", {"scope": "Actual restarted disposable HTTP application, not blind quality", **counts, "sse_matches_normal_answer": True, "sse_tokens_match_terminal": True, "early_disconnect": "interrupted"})
print(json.dumps(counts | {"sse_parity": True, "early_disconnect": "interrupted"}))
