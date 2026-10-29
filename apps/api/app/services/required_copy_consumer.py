"""Pure descriptor replay after the staged caller's independent source guard."""

import hashlib
from copy import deepcopy

from app.services import contextual_source_proof as body
from app.services.required_copy_source import CONTRACT, METHOD, proof_record


def recorded_copy(proof):
    """Recorded structural lineage only; never a source/NLI/permission grant."""
    from app.evidence_policy import reading_version

    body._same(proof["contract"], reading_version("contextual_source_v3").procedure)
    body._same(proof["method"], METHOD)
    body._same(proof["inventory"]["reading_profile"], "contextual_source_v3")
    required = proof["required_copy"]
    body._same(required["contract"], CONTRACT)
    body._same(required, proof["inventory"]["required_copy"])
    documents = required["documents"]
    if type(documents) is not list or not 1 <= len(documents) <= 8:
        raise body.SourceGuardError("Recorded required-copy document budget invalid")
    ids = [d["identity"]["document_id"] for d in documents]
    if len(set(ids)) != len(ids):
        raise body.SourceGuardError("Recorded required-copy source duplicated")
    body._same(ids, required["ordered_document_ids"])
    body._same(required["root_identity"], documents[0]["identity"])
    body._same(proof["source_body"], documents[0]["body"])
    body._same(proof["fragments"], [f for d in documents for f in d["fragments"]])
    body._same(required["separator"], "\n\n")
    rendered = "\n\n".join(d["body"] for d in documents)
    body._same(rendered, required["rendered_text"])
    closure = required["structural_closure"]
    body._same(ids, closure["ordered_document_ids"])
    body._same(rendered, closure["rendered_text"])
    for document in documents:
        _recorded_document(document)
    return required


def _recorded_document(document):
    identity = document["identity"]
    if (
        type(identity["document_version"]) is not int
        or identity["document_version"] < 1
    ):
        raise body.SourceGuardError("Recorded required-copy version invalid")
    body._same(
        identity["content_hash"], hashlib.sha256(document["body"].encode()).hexdigest()
    )
    cursor = 0
    for part in document["fragments"]:
        body._same({k: part[k] for k in identity}, identity)
        points = [
            part[k]
            for k in ("chunk_start", "chunk_end", "document_start", "document_end")
        ]
        if not all(type(p) is int for p in points) or not (
            0 <= points[0] < points[1]
            and points[2] == cursor < points[3] <= len(document["body"])
            and points[1] - points[0] == points[3] - points[2]
        ):
            raise body.SourceGuardError(
                "Recorded required-copy fragment coverage invalid"
            )
        cursor = part["document_end"]
    body._same(cursor, len(document["body"]))


def fragments_lineage(proof, known, contexts):
    from app.services.requirement_contract import _fragment_in_source, _same_document

    try:
        required = recorded_copy(proof)
        for document in required["documents"]:
            identity = document["identity"]
            sources = [
                source
                for context in contexts
                if type(context) is dict and _same_document(context, identity)
                for source in context.get("sources", [])
                if type(source) is dict
            ]
            for part in document["fragments"]:
                actual = known.get(part["chunk_id"])
                if type(actual) is not dict or not _same_document(actual, identity):
                    return False
                if not any(
                    s.get("chunk_id") == part["chunk_id"]
                    and _same_document(s, identity)
                    and _fragment_in_source(part, s)
                    for s in sources
                ):
                    return False
        return True
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return False


def witness_mapping(witness, proof):
    try:
        required = recorded_copy(proof)
        body._same(witness["value"], required["rendered_text"])
        root = required["documents"][0]
        part = next(
            p for p in root["fragments"] if p["chunk_id"] == witness["chunk_id"]
        )
        body._same(
            witness["span"],
            {
                "start": part["chunk_start"],
                "end": part["chunk_end"],
                "text": root["body"][part["document_start"] : part["document_end"]],
            },
        )
        body._same(
            witness["document_range"],
            {"start": part["document_start"], "end": part["document_end"]},
        )
        return True
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration):
        return False


def reconstruct_required_copy_group(
    selection, requirement, snapshots, plan, settings, *, guard
):
    """No context-free certifier: require the separately replayed source guard."""
    consumer = guard["consumer_proof"]
    body._same(consumer["method"], METHOD)
    required = consumer["required_copy"]
    body._same(required["contract"], CONTRACT)
    body._same(consumer["request_plan_sha256"], body._digest(plan.record()))
    body._same(consumer["support_settings"], body._support(selection))
    body._same(
        consumer["support_settings"],
        body._support({"evidence_support": settings["support"]}),
    )
    for document in required["documents"]:
        snapshot = snapshots[document["identity"]["document_id"]]
        body._same(document["identity"], body._snapshot_identity(snapshot))
        body._same(document["body"], snapshot["body"])
    identifier = requirement.id
    candidates = [
        r
        for r in selection["candidates"]
        if r.get("requirement_id") == identifier
        and r.get("procedure_completeness", {}).get("method") == METHOD
        and r.get("source_guard_record", {}).get("source_identity")
        == required["root_identity"]
    ]
    if len(candidates) != 1:
        raise body.SourceGuardError(
            "One independently reconstructed required-copy candidate required"
        )
    candidate = candidates[0]
    proof = candidate["procedure_completeness"]
    expected = proof_record(candidate["proposal"], consumer["envelope_inventory"])
    body._same(proof, expected)
    origins = [
        p
        for p in selection["proposals"]
        if p.get("requirement_id") == identifier
        and p.get("document_id") == required["root_identity"]["document_id"]
    ]
    if not origins:
        raise body.SourceGuardError("Required-copy raw proposal origins missing")
    return {
        "descriptor": {"procedure_completeness": deepcopy(proof)},
        "value": required["rendered_text"],
        "margin": consumer["entailment_margin"],
        "supported": consumer["supported"],
        "source_guard": deepcopy(guard),
        "origins": deepcopy(origins),
        "fragments": deepcopy(proof["fragments"]),
    }
