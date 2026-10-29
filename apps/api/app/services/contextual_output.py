"""Pure, factual-only contextual output/history reconstruction.

Callers supply authoritative immutable snapshots and an independently retained
query capture. Recorded logits are replayed, never inferred here. This verifier
does not authorize sources, run models, or certify procedure/role semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

from app.evidence_policy import reading_version
from app.services.answer_requirements import plan_requirements
from app.services.contextual_publication import stable_capture, validate_inventory
from app.services.contextual_values import contextual_value_identity
from app.services.evidence_proposals import (
    QAObservation,
    make_proposal,
    qa_raw_candidates,
)
from app.services.procedure_output import (
    RENDERER,
    render_extractive,
    retained_selection,
)
from app.services.requirement_binding import condition_relation, support_claim
from app.services.requirement_contract import (
    _CONDITION_READER_FIELDS,
    condition_model_settings,
    valid_condition_assessment,
    valid_condition_model_settings,
    validate_discovery_lineage,
)
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

_FACTUAL = frozenset(
    {"duration", "quantity", "location", "boolean", "start_time", "weekday"}
)
_ASSESSMENT = frozenset(
    {"label", "logits", "entailment_margin", "supported", "pair_tokens"}
)
_PRESENTATION = frozenset(
    {"contextual_output_certificate", "presentation_verification"}
)


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _same(actual, expected, reason):
    if _json(actual) != _json(expected):
        raise ValueError(reason)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _interval(value, content):
    if (
        type(value) is not dict
        or set(value) != {"start", "end"}
        or type(value["start"]) is not int
        or type(value["end"]) is not int
        or not 0 <= value["start"] < value["end"] <= len(content)
    ):
        raise ValueError("Invalid source interval")
    return value["start"], value["end"]


def _literal_range(text, content, start, end):
    if start is None and end is None:
        start = content.find(text)
        if start < 0 or content.find(text, start + 1) >= 0:
            raise ValueError("Ambiguous supporting premise")
        end = start + len(text)
    interval = {"start": start, "end": end}
    a, b = _interval(interval, content)
    if content[a:b] != text:
        raise ValueError("Supporting premise differs from actual source")
    return {"start": a, "end": b}


def _source_inventory(snapshots, *, max_documents=64):
    if (
        type(max_documents) is not int
        or max_documents < 1
        or type(snapshots) is not dict
        or not 1 <= len(snapshots) <= max_documents
    ):
        raise ValueError("Immutable snapshots required")
    chunks, inventory = {}, []
    for document_id, snapshot in sorted(snapshots.items()):
        body = snapshot["body"]
        identity = {
            k: snapshot[k] for k in ("document_id", "document_version", "content_hash")
        }
        source_identity = dict(identity)
        if "workspace_id" in snapshot:
            source_identity["workspace_id"] = snapshot["workspace_id"]
        if (
            type(document_id) is not str
            or not document_id
            or identity["document_id"] != document_id
            or type(identity["document_version"]) is not int
            or identity["document_version"] < 1
            or type(body) is not str
            or not body
            or len(body.encode("utf-8")) > 128 * 1024
            or identity["content_hash"] != _hash(body)
        ):
            raise ValueError("Immutable source identity/body mismatch")
        manifest = snapshot["chunks"]
        if type(manifest) is not list or not 1 <= len(manifest) <= 64:
            raise ValueError("Immutable chunk inventory invalid")
        located, indices, parts = [], set(), []
        source = SimpleNamespace(body=body, identity=source_identity, chunks=located)
        for item in sorted(manifest, key=lambda row: row["index"]):
            identifier, index, content = item["id"], item["index"], item["content"]
            if (
                type(identifier) is not str
                or not identifier
                or identifier in chunks
                or type(index) is not int
                or index < 0
                or index in indices
                or type(content) is not str
                or not content
            ):
                raise ValueError("Immutable chunk identity invalid")
            first = body.find(content)
            if first < 0 or body.find(content, first + 1) >= 0:
                raise ValueError("Immutable chunk mapping missing or ambiguous")
            last = first + len(content)
            if located and (first <= located[-1].start or last <= located[-1].end):
                raise ValueError("Immutable chunk ordering invalid")
            chunk = SimpleNamespace(
                id=identifier,
                document_id=document_id,
                content=content,
                metadata=identity,
            )
            located.append(SimpleNamespace(chunk=chunk, start=first, end=last))
            indices.add(index)
            chunks[identifier] = {
                "chunk": chunk,
                "source": source,
                "start": first,
                "identity": {"chunk_id": identifier, **identity},
                "metadata": snapshot.get("metadata", {}),
            }
            parts.append(
                {
                    "id": identifier,
                    "index": index,
                    "content": content,
                    "document_range": {"start": first, "end": last},
                }
            )
        inventory.append(
            {
                **identity,
                "workspace_id": snapshot.get("workspace_id"),
                "body": body,
                "chunks": parts,
                "metadata": snapshot.get("metadata", {}),
            }
        )
    return chunks, inventory


def _observation(proposal, requirement, selection, content):
    matches = [
        r
        for r in selection["qa_observations"]
        if r["observation_id"] == proposal["qa_observation_id"]
    ]
    if len(matches) != 1:
        raise ValueError("Selected QA observation missing or duplicated")
    record = matches[0]
    reader = record["reader"]
    if (
        record["requirement_id"] != requirement.id
        or record["chunk_id"] != proposal["chunk_id"]
        or record["question"] != requirement.question
    ):
        raise ValueError("Actual QA input/settings differ from planned request")
    _same(
        reader["contract"], selection["reader_contract"], "QA reader identity mismatch"
    )
    shared = set(_CONDITION_READER_FIELDS) & reader.keys()
    if not {"mode", "model", "revision", "threshold"} <= shared:
        raise ValueError("Actual QA reader settings missing")
    _same(
        {k: reader[k] for k in shared},
        {k: selection[k] for k in shared},
        "Actual QA reader settings differ from recorded model inputs",
    )
    payload = _json(
        {k: record[k] for k in ("span", "diagnostics", "question", "reader")}
    )
    # QAObservation.capture uses the default JSON separators, not the certificate's.
    payload = json.dumps(json.loads(payload), sort_keys=True, allow_nan=False)
    expected_id = _hash(f"{requirement.id}:{proposal['chunk_id']}:{payload}")
    if record["observation_id"] != expected_id:
        raise ValueError("QA observation identity differs from actual captured input")
    choices = _validated_qa_spans(record, content)
    raw = [
        r
        for r in choices
        if r.get("start") == proposal["chunk_range"]["start"]
        and r.get("end") == proposal["chunk_range"]["end"]
    ]
    if len(raw) != 1:
        raise ValueError("Selected raw QA proposal missing or ambiguous")
    margin = raw[0]["null_margin"]
    if (
        isinstance(margin, bool)
        or not isinstance(margin, (int, float))
        or not math.isfinite(margin)
        or margin > selection["threshold"]
    ):
        raise ValueError("Selected QA proposal fails recorded null threshold")
    return QAObservation(
        expected_id, requirement.id, proposal["chunk_id"], payload
    ), margin


def _validated_qa_spans(record, content):
    span = record["span"]
    if type(span) is not dict or set(span) != {"start", "end", "text"}:
        raise ValueError("Captured QA observation span schema invalid")
    left, right = _interval({k: span[k] for k in ("start", "end")}, content)
    if span["text"] != content[left:right]:
        raise ValueError("Captured QA observation span differs from actual source")
    choices = qa_raw_candidates(record["diagnostics"])
    for choice in choices:
        left, right = _interval({k: choice[k] for k in ("start", "end")}, content)
        if "text" in choice and choice["text"] != content[left:right]:
            raise ValueError("Raw QA diagnostic span differs from actual source")
    return choices


def _assessment(record, settings, *, positive=True):
    if type(record) is not dict or set(record) != _ASSESSMENT:
        raise ValueError("Recorded NLI schema rejected")
    logits = record["logits"]
    if (
        not isinstance(logits, (list, tuple))
        or len(logits) != 3
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in logits)
        or type(record["pair_tokens"]) is not int
        or not 0 < record["pair_tokens"] <= settings["support"]["max_pair_tokens"]
    ):
        raise ValueError("Recorded NLI numeric inputs rejected")
    margin = logits[1] - max(logits[0], logits[2])
    expected = margin > 0 and margin >= settings["support"]["minimum_entailment_margin"]
    if (
        type(record["entailment_margin"]) not in (int, float)
        or not math.isfinite(record["entailment_margin"])
        or record["entailment_margin"] != margin
        or record["label"] != NLI.labels[max(range(3), key=lambda i: logits[i])]
        or record["supported"] is not expected
        or (positive and not valid_condition_assessment(record, settings))
    ):
        raise ValueError("Recorded NLI logits/decision rejected")
    return deepcopy(record)


def _witness(
    requirement, witness, proposal, selection, chunks, settings, *, allow_rejected=False
):
    entry = chunks[proposal["chunk_id"]]
    chunk, source = entry["chunk"], entry["source"]
    raw_start, raw_end = _interval(proposal["chunk_range"], chunk.content)
    observation, margin = _observation(proposal, requirement, selection, chunk.content)
    rebuilt = make_proposal(
        requirement.id,
        source,
        chunk,
        raw_start,
        raw_end,
        origin="qa_reader",
        observation=observation,
    ).record()
    _same(proposal, rebuilt, "Raw proposal identity/source lineage mismatch")
    claim = support_claim(
        requirement,
        chunk.content,
        raw_start,
        raw_end,
        reading_profile="contextual_source_v1",
    )
    if claim.rejection or not claim.hypothesis or claim.proof_edges:
        raise ValueError("Unsupported contextual factual binding or special proof edge")
    relation = condition_relation(requirement, chunk.content, entry["metadata"])
    if relation != "applies":
        raise ValueError("Source condition not established for factual request")
    primary = _literal_range(
        claim.premise, chunk.content, claim.premise_start, claim.premise_end
    )
    support = {"start": claim.support_start, "end": claim.support_end}
    left, right = _interval(support, chunk.content)
    check_ranges = [
        _literal_range(c.premise, chunk.content, c.start, c.end) for c in claim.checks
    ]
    if not any(
        r["start"] <= raw_start < raw_end <= r["end"] for r in [primary, *check_ranges]
    ):
        raise ValueError("Raw accepted QA context not verified")
    expected_span = {**support, "text": chunk.content[left:right]}
    document_range = {
        "start": entry["start"] + left,
        "end": entry["start"] + right,
    }
    expected_witness = {
        **entry["identity"],
        "value": claim.value,
        "span": expected_span,
        "document_range": document_range,
        "proof_edges": [],
    }
    if witness is not None:
        for key, expected in expected_witness.items():
            _same(
                witness[key],
                expected,
                "Actual factual witness differs from reconstructed claim",
            )
    diagnostics = [
        c
        for c in selection["candidates"]
        if c.get("proposal", {}).get("proposal_id") == proposal["proposal_id"]
        and "support" in c
    ]
    if len(diagnostics) != 1:
        raise ValueError("Selected raw proposal has no unique assessed candidate")
    candidate = diagnostics[0]
    expected = {
        **entry["identity"],
        "requirement_id": requirement.id,
        "raw_span": proposal["chunk_range"],
        "null_margin": margin,
        "hypothesis": claim.hypothesis,
        "validated_answer_span": {
            "start": claim.start,
            "end": claim.end,
            "text": claim.value,
        },
        "condition": relation,
        "primary_support_range": primary,
        "proof_edges": [],
        "origin": "qa_reader",
        "proposal": proposal,
    }
    for key, value in expected.items():
        _same(
            candidate[key],
            value,
            "Selected candidate model-input/source binding mismatch",
        )
    decision = _assessment(candidate["support"], settings, positive=not allow_rejected)
    if witness is not None:
        _same(
            witness["entailment_margin"],
            decision["entailment_margin"],
            "Witness NLI margin mismatch",
        )
    pairs = _support_pairs(
        claim,
        candidate,
        settings,
        primary,
        check_ranges,
        decision,
        allow_rejected=allow_rejected,
    )
    if not _accepted_candidate(candidate, pairs, witness, allow_rejected):
        return None
    return dict(
        requirement_id=requirement.id,
        proposal_id=proposal["proposal_id"],
        **entry["identity"],
        chunk_range=support,
        document_range=document_range,
        text=expected_span["text"],
        value=claim.value,
        raw_range=proposal["chunk_range"],
        nli_pairs=pairs,
    )


def _accepted_candidate(candidate, pairs, witness, allow_rejected):
    supported = all(pair["assessment"]["supported"] for pair in pairs)
    if candidate["decision"] != ("supported" if supported else "support_rejected"):
        raise ValueError(
            "Retained candidate decision differs from reconstructed checks"
        )
    if not supported and (witness is not None or not allow_rejected):
        raise ValueError("Selected witness has rejected mandatory support")
    return supported


def _support_pairs(
    claim, candidate, settings, primary, check_ranges, decision, *, allow_rejected=False
):
    checks = candidate["support_checks"]
    if type(checks) is not list or len(checks) != len(claim.checks):
        raise ValueError("Mandatory factual support checks missing or invented")
    pairs = [
        {
            "premise": claim.premise,
            "hypothesis": claim.hypothesis,
            "source_range": primary,
            "assessment": decision,
        }
    ]
    for check, record, interval in zip(claim.checks, checks, check_ranges, strict=True):
        expected = {
            "name": check.name,
            "hypothesis": check.hypothesis,
            "source_range": interval,
        }
        if set(record) != set(expected) | _ASSESSMENT:
            raise ValueError("Mandatory factual support-check schema invalid")
        for key, value in expected.items():
            _same(
                record[key],
                value,
                "Mandatory factual check differs from actual source/claim",
            )
        pairs.append(
            {
                **expected,
                "premise": check.premise,
                "assessment": _assessment(
                    {k: record[k] for k in _ASSESSMENT},
                    settings,
                    positive=not allow_rejected,
                ),
            }
        )
    return pairs


def _passages(fragments, chunks):
    """Same literal witness union used by the existing extractive renderer."""
    result = {}
    for fragment in fragments:
        result.setdefault(fragment["chunk_id"], []).append(fragment["chunk_range"])
    for identifier, intervals in result.items():
        content = chunks[identifier]["chunk"].content
        merged = []
        for span in sorted(intervals, key=lambda s: (s["start"], s["end"])):
            left, right = span["start"], span["end"]
            if merged and (
                left <= merged[-1]["end"]
                or re.fullmatch(
                    r"[\s,;]*(?:(?:and|but|whereas|while)\s*)?",
                    content[merged[-1]["end"] : left],
                    re.I,
                )
            ):
                previous = merged.pop()
                left = previous["start"]
                right = max(right, previous["end"])
            merged.append({"start": left, "end": right, "text": content[left:right]})
        result[identifier] = merged
    return result


def _capture_settings(selection, question, answer, citations, query_context, version):
    if (
        selection["contract"] != version.requirement
        or selection.get("decision") != "answer"
        or type(question) is not str
        or type(answer) is not str
        or type(citations) is not list
    ):
        raise ValueError("Actual contextual factual presentation required")
    if type(selection.get("conflicts")) is not list:
        raise ValueError("Explicit factual conflict context must be a list")
    for key in (
        "procedure_contexts",
        "role_scope_read_set",
        "role_scope_interpretations",
        "role_scope_findings",
        "conflicts",
    ):
        if selection.get(key):
            raise ValueError(
                "Procedure/role/conflict context not supported by factual-only verifier"
            )
    if any(p.get("origin") != "qa_reader" for p in selection["proposals"]):
        raise ValueError("Factual source-pattern origin is not implemented")
    captured = retained_selection(query_context)
    if captured is None:
        raise ValueError("Independently retained execution capture required")
    actual_capture = stable_capture(selection, _PRESENTATION)
    retained_capture = stable_capture(captured, _PRESENTATION)
    _same(
        actual_capture,
        retained_capture,
        "Factual model/source capture differs from retained execution",
    )
    if validate_discovery_lineage(selection).get("valid") is not True:
        raise ValueError("Recorded QA/source discovery lineage rejected")
    settings = condition_model_settings(
        selection,
        selection["evidence_support"],
        selection,
        selection["evidence_profile"],
        "extractive",
    )
    if not valid_condition_model_settings(settings, selection):
        raise ValueError("Recorded reader/NLI model settings rejected")
    _same(
        settings["support"]["batch_size"],
        BATCH_SIZE,
        "NLI batch setting identity mismatch",
    )
    _same(
        settings["support"]["max_pair_tokens"],
        MAX_PAIR_TOKENS,
        "NLI token setting identity mismatch",
    )
    return settings, retained_capture


def _inspected_sources(selection, chunks, source_snapshots):
    inspected = selection["inspected_sources"]
    if type(inspected) is not list or len({r["chunk_id"] for r in inspected}) != len(
        inspected
    ):
        raise ValueError("Inspected source inventory invalid")
    for member in inspected:
        _same(
            member,
            chunks[member["chunk_id"]]["identity"],
            "Actual inspected source identity mismatch",
        )
    if {r["document_id"] for r in inspected} != set(source_snapshots):
        raise ValueError(
            "Actual snapshot document inventory differs from inspected sources"
        )


def _request_row(row, requirement):
    if (
        requirement.kind not in _FACTUAL
        or requirement.depends_on
        or row.get("procedure_completeness")
    ):
        raise ValueError("Unsupported request kind/dependency in factual-only verifier")
    expected = {
        "id": requirement.id,
        "kind": requirement.kind,
        "original_text": requirement.original_text,
        "input_range": {
            "start": requirement.input_start,
            "end": requirement.input_end,
        },
        "prepared_question": requirement.question,
        "source_workspace": requirement.source_workspace,
        "depends_on": list(requirement.depends_on),
        "status": "supported",
    }
    for key, value in expected.items():
        _same(row[key], value, "Whole actual prepared request/range mismatch")


def _retained_candidates(selection, proposals, planned):
    """Bind all assessed candidate records before grouping by a producer's tag."""
    required = {r.id for r in planned}
    result = {}
    for candidate in selection["candidates"]:
        if type(candidate) is not dict:
            raise ValueError("Retained candidate schema invalid")
        if "support" not in candidate and candidate.get("decision") != "supported":
            continue
        origin = candidate["proposal"]
        proposal = proposals[origin["proposal_id"]]
        _same(
            origin, proposal, "Retained assessed candidate proposal inventory mismatch"
        )
        identifier = candidate["requirement_id"]
        if identifier not in required or identifier != proposal["requirement_id"]:
            raise ValueError("Retained supported candidate request binding invalid")
        result.setdefault(identifier, []).append(proposal)
    return result


def _retained_witness_proposal(witness, requirement, proposals):
    origins = witness["proposals"]
    if (
        len(origins) != 1
        or witness.get("procedure_completeness")
        or witness.get("proof_edges")
    ):
        raise ValueError("Duplicate/raw-origin or special witness not supported")
    proposal = proposals[origins[0]["proposal_id"]]
    _same(origins[0], proposal, "Retained witness raw proposal differs from inventory")
    if proposal["requirement_id"] != requirement.id:
        raise ValueError("Retained raw proposal belongs to another requirement")
    return proposal


def _selected_row(
    row,
    requirement,
    selection,
    proposals,
    selected,
    used,
    chunks,
    settings,
    retained_candidates,
):
    facts, found = {}, []
    for witness in row["witnesses"]:
        proposal = _retained_witness_proposal(witness, requirement, proposals)
        identifier = proposal["proposal_id"]
        if identifier in facts:
            raise ValueError("Duplicate retained factual witness")
        fact = _witness(requirement, witness, proposal, selection, chunks, settings)
        assert fact is not None  # _witness rejects unsupported selected witnesses.
        facts[identifier] = fact
        if identifier in selected:
            if identifier in used:
                raise ValueError("Selected witness is duplicated across requests")
            found.append(fact)
            used.add(identifier)
    for proposal in retained_candidates.get(requirement.id, []):
        identifier = proposal["proposal_id"]
        if identifier not in facts:
            fact = _witness(
                requirement,
                None,
                proposal,
                selection,
                chunks,
                settings,
                allow_rejected=True,
            )
            if fact is not None:
                facts[identifier] = fact
    if (
        len(
            {contextual_value_identity(requirement, f["value"]) for f in facts.values()}
        )
        > 1
    ):
        raise ValueError(
            "Conflicting retained supported factual values require separate handling"
        )
    if not found:
        raise ValueError("Every requested fact needs a selected assessed witness")
    return found, list(facts.values())


def _selected_facts(selection, planned, chunks, settings):
    proposals = {p["proposal_id"]: p for p in selection["proposals"]}
    selected = selection["selected_proposal_ids"]
    if (
        type(selected) is not list
        or not selected
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("Selected raw proposal inventory missing or duplicated")
    rows = selection["requirements"]
    if type(rows) is not list or not planned or len(rows) != len(planned):
        raise ValueError("Whole actual request inventory mismatch")
    retained_candidates = _retained_candidates(selection, proposals, planned)
    fragments, request_plan, used, supported_inventory = [], [], set(), []
    for row, requirement in zip(rows, planned, strict=True):
        _request_row(row, requirement)
        request_plan.append(
            {**asdict(requirement), "prepared_question": requirement.question}
        )
        chosen, retained = _selected_row(
            row,
            requirement,
            selection,
            proposals,
            selected,
            used,
            chunks,
            settings,
            retained_candidates,
        )
        fragments.extend(chosen)
        supported_inventory.extend(retained)
    if used != set(selected):
        raise ValueError("Selected raw proposal inventory is not exactly discharged")
    return fragments, request_plan, supported_inventory


def _canonical_citations(citations, fragments, chunks):
    passages = _passages(fragments, chunks)
    if len(citations) != len(passages):
        raise ValueError("Actual citation count differs from selected passages")
    canonical = []
    for index, (citation, identifier) in enumerate(
        zip(citations, passages, strict=True), 1
    ):
        entry = chunks[identifier]
        expected = dict(
            citation_index=index,
            **entry["identity"],
            quoted_text=entry["chunk"].content,
            answer_spans=passages[identifier],
        )
        for key, value in expected.items():
            _same(
                citation[key],
                value,
                "Actual citation order/source/spans differ from canonical witnesses",
            )
        canonical.append(expected)
    return canonical


def _answer_ranges(canonical, fragments):
    cursor = len(render_extractive([])[0])
    for citation in canonical:
        for span in citation["answer_spans"]:
            for fragment in fragments:
                interval = fragment["chunk_range"]
                if (
                    fragment["chunk_id"] == citation["chunk_id"]
                    and span["start"]
                    <= interval["start"]
                    < interval["end"]
                    <= span["end"]
                ):
                    first = cursor + interval["start"] - span["start"]
                    fragment["answer_range"] = {
                        "start": first,
                        "end": first + len(fragment["text"]),
                    }
            cursor += len(span["text"]) + 1
        cursor += len(f" [{citation['citation_index']}]") + 1


def _reconstruct(
    selection, *, question, answer, citations, source_snapshots, query_context
):
    version = reading_version("contextual_source_v1")
    planned = plan_requirements(question, reading_profile=version.profile)
    if any(r.kind not in _FACTUAL or r.depends_on for r in planned):
        raise ValueError("Unsupported request kind/dependency in factual-only verifier")
    settings, retained_capture = _capture_settings(
        selection, question, answer, citations, query_context, version
    )
    chunks, inventory = _source_inventory(source_snapshots)
    _inspected_sources(selection, chunks, source_snapshots)
    publication_inventory = validate_inventory(selection, chunks, source_snapshots)
    fragments, request_plan, supported_inventory = _selected_facts(
        selection, planned, chunks, settings
    )
    canonical = _canonical_citations(citations, fragments, chunks)
    expected_answer, _ = render_extractive(canonical)
    if answer != expected_answer:
        raise ValueError("Actual answer differs from existing extractive renderer")
    _answer_ranges(canonical, fragments)
    return {
        "contract": version.output,
        "reading_profile": version.profile,
        "renderer": RENDERER,
        "request_plan_contract": version.request_plan,
        "question_sha256": _hash(question),
        "answer_sha256": _hash(answer),
        "source_inventory": inventory,
        "publication_inventory": publication_inventory,
        "request_plan": request_plan,
        "model_settings": settings,
        "selected_proposal_ids": list(selection["selected_proposal_ids"]),
        "selected_fragments": fragments,
        "supported_fact_inventory": supported_inventory,
        "citations": canonical,
        "retained_capture_sha256": _hash(_json(retained_capture)),
    }


def reconstruct_certificate(
    selection, *, question, answer, citations, source_snapshots, query_context
):
    """Rebuild a factual certificate from actual inputs; never mutate its producer."""
    try:
        return deepcopy(
            _reconstruct(
                selection,
                question=question,
                answer=answer,
                citations=citations,
                source_snapshots=source_snapshots,
                query_context=query_context,
            )
        )
    except (
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        AttributeError,
        StopIteration,
        RecursionError,
        UnicodeError,
        OverflowError,
    ) as exc:
        raise ValueError(f"Contextual factual output rejected: {exc}") from exc


def certify_output(selection, **context):
    """Stage a certificate only after full actual presentation reconstruction."""
    selection["contextual_output_certificate"] = reconstruct_certificate(
        selection, **context
    )


def verify_output(selection, **context):
    """Saved history must reproduce its actual certificate; missing is not legacy."""
    try:
        expected = reconstruct_certificate(selection, **context)
        return _json(selection.get("contextual_output_certificate")) == _json(expected)
    except (ValueError, TypeError, RecursionError):
        return False
