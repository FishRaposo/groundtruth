"""Real HTTP restart/asset-failure checks against a cloned disposable database."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("missing", "repaired"), required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    output = here / args.phase
    output.mkdir()
    seed = json.loads((here / "data/seed-manifest.json").read_text(encoding="utf-8"))
    origin = seed["api_url"].rstrip("/")
    assert urlparse(origin).netloc == "127.0.0.1:8402"
    secrets = [item["api_key"] for item in seed["principals"].values()]

    def save(name, value):
        text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        assert not any(secret in text for secret in secrets)
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(text)

    before = here.parent / "connected-visual-v298/records-before-restart"
    originals = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in before.glob("*.json")
        if "-source-" not in path.stem
    }
    assert len(originals) == 12
    with httpx.Client(
        base_url=origin + "/api",
        headers={"X-API-Key": seed["principals"]["admin-a"]["api_key"]},
        timeout=120,
        trust_env=False,
    ) as client:
        def get(route):
            response = client.get(route)
            assert response.status_code == 200, (route, response.status_code)
            return response.json()

        initial_health = get("/health")
        save("health-before-history.json", initial_health)
        assert initial_health["runtime"]["evidence_support"]["readiness"] == "not_loaded"
        citations = 0
        for identifier, expected in originals.items():
            actual = get(f"/queries/{identifier}")
            save(f"history-{identifier}.json", actual)
            assert actual == expected, f"Recorded presentation changed: {identifier}"
            for source in expected["sources"]:
                index = source["citation_index"]
                current_source = get(f"/queries/{identifier}/sources/{index}")
                expected_source = json.loads(
                    (before / f"{identifier}-source-{index}.json").read_text(encoding="utf-8")
                )
                save(f"history-{identifier}-source-{index}.json", current_source)
                assert current_source == expected_source
                citations += 1
        after_history = get("/health")
        save("health-after-history.json", after_history)
        assert after_history["runtime"]["evidence_support"]["readiness"] == "not_loaded"

        readiness = client.get("/health/ready")
        save("readiness.json", {"status": readiness.status_code, "body": readiness.json()})
        assert readiness.status_code == (503 if args.phase == "missing" else 200)
        assert readiness.json()["checks"]["evidence_support"] == (
            "error" if args.phase == "missing" else "ok"
        )
        cedar = next(
            row for row in originals.values()
            if row["outcome"] == "completed" and "Cedar" in row["question"]
        )
        payload = {
            "question": cedar["question"],
            "document_ids": [cedar["sources"][0]["document_id"]],
            "retrieval_method": "keyword",
        }
        save("request.json", payload)
        normal = client.post("/queries", json=payload)
        save("normal.json", {"status": normal.status_code, "body": normal.json()})
        stream = client.post("/queries/stream", json=payload)
        if stream.status_code == 200:
            events = [
                json.loads(line[5:].strip()) for line in stream.text.splitlines()
                if line.startswith("data:")
            ]
        else:
            events = []
        save("stream.json", {
            "status": stream.status_code,
            "events": events,
            "error": stream.json() if stream.status_code != 200 else None,
        })
        if args.phase == "missing":
            assert normal.status_code == 503
            assert stream.status_code == 503 or any(item.get("type") == "error" for item in events)
            assert not any(item.get("type") in {"token", "citations", "done"} for item in events)
            new_rows = [
                row for row in get("/queries?limit=100")["queries"]
                if row["id"] not in originals and row["question"] == payload["question"]
            ]
            assert len(new_rows) == 2
            for row in new_rows:
                record = get(f"/queries/{row['id']}")
                save(f"new-error-{row['id']}.json", record)
                assert record["outcome"] == "error"
                assert record["answer"] is None and record["sources"] == []
                assert record["refused"] is False
        else:
            assert normal.status_code == stream.status_code == 200
            done = [item for item in events if item.get("type") == "done"]
            assert len(done) == 1
            normal_body = normal.json()
            for record in (normal_body, done[0]):
                assert record["outcome"] == "completed" and record["refused"] is False
                assert record["answer"] == cedar["answer"]
                assert record["sources"] == cedar["sources"]
                assert record["provenance"]["answer_selection"]["presentation_verification"]["status"] == "verified"
            assert not any(item.get("type") == "error" for item in events)
        for identifier, expected in originals.items():
            assert get(f"/queries/{identifier}") == expected
        save("result.json", {
            "phase": args.phase,
            "history_records_unchanged": 12,
            "citation_snapshots_unchanged": citations,
            "historical_gets_loaded_support_model": False,
            "normal_status": normal.status_code,
            "stream_status": stream.status_code,
            "scope": "Actual HTTP on database clone; synthetic engineering examples only",
        })
    print(json.dumps({"phase": args.phase, "history": 12, "citations": citations, "passed": True}))


if __name__ == "__main__":
    main()
