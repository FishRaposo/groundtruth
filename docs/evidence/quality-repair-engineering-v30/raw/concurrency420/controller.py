"""Three simultaneous real reader requests with distinct private SQL scopes."""
import concurrent.futures
import json
from pathlib import Path

import httpx

q = Path(__file__).resolve().parent
out = q / "typed-concurrency-http-v420"
assert not out.exists()
out.mkdir()
seed = json.loads((q / "typed-connected-live-v378/private/seed.json").read_text())
inputs = json.loads((q / "typed-connected-inputs-v360/manifest.json").read_text())
assert seed["api_url"] == "http://127.0.0.1:8401"
secrets = [item["api_key"] for item in seed["principals"].values()]


def run(width):
    project = seed["typed_connected_v360"]["projects"][width]
    allowed = {item["document_id"] for item in project["documents"].values()}
    primary = project["documents"]["typed-lumen-procedure"]["document_id"]
    headers = {"X-API-Key": seed["principals"][project["principal_alias"]]["api_key"]}
    with httpx.Client(base_url=seed["api_url"], headers=headers, timeout=300) as client:
        conversation = client.post("/api/conversations", json={"title": "Disposable concurrent scope " + width})
        conversation.raise_for_status()
        response = client.post("/api/queries", json={"question": inputs["question"], "retrieval_method": "keyword", "top_k": 5, "conversation_id": conversation.json()["id"]})
        response.raise_for_status()
        record = response.json()
        assert record["outcome"] == "completed" and record["refused"] is False
        assert "Place two tokens" in record["answer"]
        assert {source["document_id"] for source in record["sources"]} == {primary}
        assert all(source["document_version"] == 2 for source in record["sources"])
        assert {score["document_id"] for score in record["retrieval_trace"]["scores"]} <= allowed
        proof = record["provenance"]["answer_selection"]["requirements"][0]["procedure_completeness"]
        assert proof["document_id"] == primary
        inspected = {item["source_identity"]["document_id"] for item in proof["condition_exclusion_inventory"]["exclusions"]}
        assert inspected == allowed - {primary}
        saved = client.get("/api/queries/" + record["id"])
        saved.raise_for_status()
        assert saved.json() == record
        text = json.dumps(record, indent=2) + "\n"
        assert not any(secret in text for secret in secrets)
        (out / ("response-" + width + ".json")).write_text(text)
        return {"cohort": width, "query_id": record["id"], "conversation_id": conversation.json()["id"], "source_ids": sorted(allowed), "completed": True, "scope_leaks": 0}


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    result = list(pool.map(run, ("390", "768", "1440")))
assert len({item["query_id"] for item in result}) == 3
assert len({item["conversation_id"] for item in result}) == 3
(out / "result.json").write_text(json.dumps({"scope": "Three overlapping credential-free CPU engineering requests; not unseen quality or load capacity", "requests": result}, indent=2) + "\n")
print(json.dumps({"completed": 3, "distinct_conversations": 3, "private_scope_leaks": 0}))
