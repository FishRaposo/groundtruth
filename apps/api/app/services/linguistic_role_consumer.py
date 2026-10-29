"""Pure role interpretation replay over caller-authenticated source snapshots.

No authorization or SQL membership check occurs here. Those checks remain the
caller's duty. Every retained candidate body is classified before role choice;
model scores never erase a session exception or unresolved governing material.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy

from app.evidence_policy import reading_version, recorded_evidence_policy
from app.services.role_scope_policy import plan_activity_role, session_role_scope

PROFILE = "contextual_source_v2"
_SUCCESS = {"consistent": True, "reason": None}
_IDENTITY = (
    "document_id",
    "workspace_id",
    "owner_id",
    "document_version",
    "content_hash",
)


def _selected_version(selection):
    profile = selection["evidence_profile"]["evidence_reading_profile"]
    if type(profile) is not str or profile not in {
        PROFILE,
        "contextual_source_v3",
        "contextual_source_v4",
    }:
        raise ValueError("Unsupported role consumer reading profile")
    return reading_version(profile)


def _same(actual, expected):
    from app.services.role_scope_inspection import _typed_read_set_equal

    if not _typed_read_set_equal(actual, expected):
        raise ValueError("Independent role scope reconstruction differs")


def stable_role_capture(selection):
    """Only a strictly successful publication recheck is a transient annotation."""
    result = deepcopy(selection)
    record = result.get("role_scope_read_set")
    if type(record) is dict and "before_publication" in record:
        _same(record.pop("before_publication"), _SUCCESS)
    return result


def _identifier(value):
    if type(value) is not str or str(uuid.UUID(value)) != value:
        raise ValueError("Role source identifier must be canonical")
    return value


def _record(snapshot):
    from app.services.role_scope_inspection import (
        MAX_ROLE_BODY_BYTES,
        MAX_ROLE_CHUNKS,
        _digest,
    )

    body, chunks, live = (
        snapshot["body"],
        snapshot["chunks"],
        snapshot["role_live_chunks"],
    )
    if (
        type(body) is not str
        or not body.strip()
        or len(body.encode()) > MAX_ROLE_BODY_BYTES
        or type(snapshot["document_version"]) is not int
        or snapshot["document_version"] < 1
        or snapshot["content_hash"] != hashlib.sha256(body.encode()).hexdigest()
        or type(snapshot["workspace_id"]) is not str
        or not snapshot["workspace_id"]
        or type(snapshot["owner_id"]) not in {str, type(None)}
        or snapshot["status"] != "ready"
        or type(snapshot["metadata"]) is not dict
        or type(chunks) is not list
        or not 1 <= len(chunks) <= MAX_ROLE_CHUNKS
        or type(live) is not list
        or len(live) != len(chunks)
    ):
        raise ValueError("Authoritative role source receipt is invalid")
    _identifier(snapshot["document_id"])
    _identifier(snapshot["snapshot_id"])
    for part, current in zip(chunks, live, strict=True):
        if (
            type(part) is not dict
            or type(current) is not dict
            or type(part["index"]) is not int
            or part["index"] < 0
            or type(part["content"]) is not str
            or not part["content"]
            or body.find(part["content"]) < 0
            or body.find(part["content"]) != body.rfind(part["content"])
            or type(current.get("metadata")) not in {dict, type(None)}
            or set(current) != {"id", "index", "content", "metadata"}
        ):
            raise ValueError("Authoritative role chunks are invalid")
        _identifier(part["id"])
        _same(
            {k: part[k] for k in ("id", "index", "content")},
            {k: current[k] for k in ("id", "index", "content")},
        )
    if len({p["id"] for p in chunks}) != len(chunks) or len(
        {p["index"] for p in chunks}
    ) != len(chunks):
        raise ValueError("Duplicate role source chunk")
    if [p["index"] for p in chunks] != sorted(p["index"] for p in chunks):
        raise ValueError("Unordered role source chunks")
    return {
        **{k: snapshot[k] for k in _IDENTITY},
        "status": "ready",
        "metadata_hash": _digest(snapshot["metadata"]),
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_chunk_hash": _digest(chunks),
        "live_chunk_hash": _digest(live),
    }


def _manifest(selection, snapshots):  # noqa: C901 - explicit captured source receipt validation
    from app.services.role_scope_inspection import (
        MAX_ROLE_BODY_BYTES,
        MAX_ROLE_CHUNKS,
        MAX_ROLE_TOTAL_BYTES,
        RoleScopeManifest,
        RoleScopeSource,
    )

    record = deepcopy(selection["role_scope_read_set"])
    if type(record) is not dict:
        raise ValueError("Complete role read set required")
    expected_keys = {
        "contract",
        "document_ids",
        "collection_ids",
        "workspace_id",
        "complete",
        "reason",
        "documents",
        "limits",
        "total_body_bytes",
        "selector",
        "index_universe",
        "after_proofs",
    }
    if set(record) != expected_keys:
        raise ValueError("Unknown or missing role read-set fields")
    _same(record["contract"], _selected_version(selection).role_manifest)
    _same(record["complete"], True)
    _same(record["reason"], None)
    _same(record.pop("after_proofs"), _SUCCESS)
    _same(
        record["limits"],
        {
            "documents": _selected_version(selection).scope_documents,
            "body_bytes": MAX_ROLE_BODY_BYTES,
            "total_body_bytes": MAX_ROLE_TOTAL_BYTES,
            "chunks_per_document": MAX_ROLE_CHUNKS,
        },
    )
    for key in ("document_ids", "collection_ids"):
        values = record[key]
        if values is not None:
            if type(values) is not list or values != sorted(set(values)):
                raise ValueError("Role read-set query selector is invalid")
            for value in values:
                _identifier(value)
    documents = record["documents"]
    if (
        type(documents) is not list
        or not 1 <= len(documents) <= record["limits"]["documents"]
    ):
        raise ValueError("Complete bounded role documents required")
    ids = [r["document_id"] for r in documents]
    if ids != sorted(set(ids)) or not set(ids) <= snapshots.keys():
        raise ValueError("Missing or duplicate authoritative role snapshot")
    total, sources = 0, []
    for origin in documents:
        snapshot = snapshots[origin["document_id"]]
        actual = _record(snapshot)
        _same(origin, actual)
        if (
            record["document_ids"] is not None
            and origin["document_id"] not in record["document_ids"]
        ):
            raise ValueError("Role document outside captured query selector")
        _same(actual["workspace_id"], record["workspace_id"])
        total += len(snapshot["body"].encode())
        sources.append(
            RoleScopeSource(
                snapshot["body"],
                json.dumps(actual, sort_keys=True),
                json.dumps(snapshot["metadata"], sort_keys=True),
            )
        )
    if total > MAX_ROLE_TOTAL_BYTES:
        raise ValueError("Role body universe exceeds the total byte budget")
    _same(record["total_body_bytes"], total)
    universe = record["index_universe"]
    if type(universe) is not list:
        raise ValueError("Complete captured role index universe required")
    seen = []
    for item in universe:
        if type(item) is not dict or set(item) != set(_IDENTITY) | {"index_hash"}:
            raise ValueError("Malformed role index identity")
        seen.append(_identifier(item["document_id"]))
        if type(item["document_version"]) is not int or item["document_version"] < 1:
            raise ValueError("Malformed role index version")
        for key in ("content_hash", "index_hash"):
            if (
                type(item[key]) is not str
                or len(item[key]) != 64
                or any(c not in "0123456789abcdef" for c in item[key])
            ):
                raise ValueError("Malformed role index hash")
        if item["document_id"] in ids:
            snapshot = snapshots[item["document_id"]]
            _same({k: item[k] for k in _IDENTITY}, {k: snapshot[k] for k in _IDENTITY})
            index = snapshot["metadata"].get("declared_source_scope")
            encoded = json.dumps(
                index, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            _same(item["index_hash"], hashlib.sha256(encoded.encode()).hexdigest())
    if seen != sorted(set(seen)) or not set(ids) <= set(seen):
        raise ValueError("Role index universe omits captured candidates")
    if (set(seen) & snapshots.keys()) - set(ids):
        raise ValueError("A retained role universe source was omitted from inspection")
    selector = record["selector"]
    if (
        type(selector) is not dict
        or selector.get("mode")
        not in {"unavailable", "sqlite_verified_source_cover_scan"}
        or type(selector.get("subjects")) is not list
    ):
        raise ValueError("Unknown role candidate selector")
    from app.services.document.declared_scope_index import _scopes

    subjects = _scopes(selection["request_plan"]["question"])
    expected_selector = {"mode": "unavailable", "subjects": subjects}
    if selector["mode"] == "sqlite_verified_source_cover_scan":
        expected_selector.update(
            mode="sqlite_verified_source_cover_scan",
            contract=reading_version("contextual_source_v1").scope_cover,
            performance="SQL compatibility scan; no indexed-scale claim",
        )
    _same(selector, expected_selector)
    return RoleScopeManifest(tuple(sources), record)


def reconstruct_role_scope(selection, requirements, snapshots):  # noqa: C901 - exhaustive original-role inventory before filtering
    """Return effective role requests and the complete canonical replay record."""
    profile = selection["evidence_profile"]
    policy = recorded_evidence_policy(profile)
    plans = {
        r.id: plan_activity_role(r, policy, request_plan=selection.get("request_plan"))
        for r in requirements
    }
    interpreted = {k: v for k, v in plans.items() if v is not None}
    for req in requirements:
        if policy.activity_roles and session_role_scope(req) and plans[req.id] is None:
            raise ValueError(
                "Qualified session role cannot fall through to activity evidence"
            )
    if not interpreted:
        if any(
            selection.get(k)
            for k in (
                "role_scope_read_set",
                "role_scope_interpretations",
                "role_scope_findings",
            )
        ) or any(
            row.get("role_scope_interpretation") or row.get("role_scope_inspection")
            for row in selection["requirements"]
        ):
            raise ValueError("Orphan role interpretation records")
        return {}, None
    from app.services.role_scope_inspection import inspect_role_contexts

    manifest = _manifest(stable_role_capture(selection), snapshots)
    from app.services.linguistic_role_closure import closure_inventory

    snapshots_for_roles = {
        source.identity["document_id"]: snapshots[source.identity["document_id"]]
        for source in manifest.sources
    }
    source_windows = closure_inventory(
        selection["role_scope_findings"],
        snapshots_for_roles,
        {
            identifier: role.prepared("session")
            for identifier, role in interpreted.items()
        },
    )
    findings, interpretations, effective, allowed, disclosures = [], [], {}, {}, []
    rows = {row["id"]: row for row in selection["requirements"]}
    for req in requirements:
        role = plans[req.id]
        if role is None:
            if rows[req.id].get("role_scope_interpretation") or rows[req.id].get(
                "role_scope_inspection"
            ):
                raise ValueError("Role evidence bound to another kind of request")
            continue
        finding = inspect_role_contexts(
            manifest,
            role,
            source_windows=source_windows,
            **(
                {"evidence_profile": profile}
                if policy.source_governance_profile == "requirement_bound_v1"
                else {}
            ),
        )
        if finding["complete"] is not True:
            raise ValueError("Whole role source universe remains unclassified")
        scope = "session" if finding["session_documents"] else "activity"
        documents = (
            finding["session_documents"]
            if scope == "session"
            else finding["activity_documents"]
        )
        if not documents:
            raise ValueError("No classified role assignment")
        interpretation = role.record(scope)
        _same(rows[req.id]["role_scope_inspection"], finding)
        _same(rows[req.id]["role_scope_interpretation"], interpretation)
        findings.append(finding)
        interpretations.append(interpretation)
        effective[req.id] = role.prepared(scope)
        allowed[req.id] = documents
        if interpretation["disclosure"]:
            disclosures.append(
                {
                    "kind": "activity_role_scope",
                    "requirement_id": req.id,
                    "text": interpretation["disclosure"],
                }
            )
    _same(selection["role_scope_findings"], findings)
    _same(selection["role_scope_interpretations"], interpretations)
    return effective, {
        "contract": _selected_version(selection).role_manifest,
        "meaning": (
            "captured authorized universe replay; no current authorization attestation"
        ),
        "read_set": manifest.record(),
        "findings": findings,
        "interpretations": interpretations,
        "allowed_documents": allowed,
        "disclosures": disclosures,
    }
