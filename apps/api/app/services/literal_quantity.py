"""Closed literal quantity syntax, not a general grammar or NLI.

No model scores grant binding. The actual request, whole immutable source, raw
span and source identity must independently rebuild the complete record.
"""

import hashlib
import json
import re
from dataclasses import asdict

from app.evidence_policy import COUNT_BINDING_CONTRACT as CONTRACT

METHOD = "complete_literal_count_field_v3"
TYPED_METHOD = "typed_atomic_count_field_v1"
STATED_METHOD = "source_stated_qualified_quantity_v1"
NUMBER = r"\d+(?:\.\d+)?"
NP = r"[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,5}"
# Scope-resolved pronouns ("its count", "does it contain") may carry the
# already-established single scope; unresolved references still fail closed.
_QUANTITY_PRONOUNS = frozenset({"it", "its", "there"})


class QuantityUnresolved(ValueError):
    pass


def _wire(value):
    return json.loads(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _np(text):
    # Literal payload identity: neither casefold nor Unicode normalization nor
    # article removal is an entity/unit alias proof. Only whitespace is syntax.
    return " ".join(text.split())


def _attribute(text):
    # The article and final "count" are recognized grammar, not payload words.
    text = re.sub(r"^(?:the|a|an)\s+", "", _np(text), flags=re.I)
    return re.sub(r"\s+count$", " count", text, flags=re.I)


def _literal(body, start, end):
    return {"start": start, "end": end, "text": body[start:end]}


def _captured_nominal(capture, raw, bounds):
    if capture is None:
        raise QuantityUnresolved("differing_noun_form_requires_actual_capture")
    from app.services.request_parser import validate_capture

    try:
        annotation = validate_capture(raw, capture)
    except (ValueError, TypeError, KeyError) as exc:
        raise QuantityUnresolved("quantity_noun_capture_does_not_reconstruct") from exc
    start, end = bounds
    tokens = [
        t
        for t in annotation["tokens"]
        if start <= t["start"] < t["end"] <= end and t["pos"] != "SPACE"
    ]
    if not tokens or tokens[0]["start"] != start or tokens[-1]["end"] != end:
        raise QuantityUnresolved("captured_counted_np_range_unclosed")
    head = tokens[-1]
    indices = {t["i"] for t in tokens}
    for token in tokens[:-1]:
        at = token
        seen = set()
        while at["i"] != head["i"]:
            if (
                at["i"] in seen
                or at["head"] not in indices
                or at["dep"] not in {"compound", "amod", "nmod", "poss", "case"}
            ):
                raise QuantityUnresolved("captured_counted_np_attachment_unclosed")
            seen.add(at["i"])
            at = annotation["tokens"][at["head"]]
    features = dict(
        field.split("=", 1) for field in head["morph"].split("|") if "=" in field
    )
    parent = annotation["tokens"][head["head"]]
    fields = ["i", "text", "start", "end", "pos", "dep", "head", "lemma", "morph"]
    return {
        "head": {key: head[key] for key in fields},
        "parent": {key: parent[key] for key in fields},
        "number": features.get("Number"),
        "capture_sha256": capture["capture_sha256"],
    }


def _unit_alignment(
    observed,
    requested,
    *,
    request_capture=None,
    source_capture=None,
    request_text="",
    source_text="",
    request_bounds=None,
    source_bounds=None,
    request_count_bounds=None,
):
    # Modifiers (including physical unit symbols) are always literal. Different
    # heads need validated captured syntax, never suffix guessing or a semantic
    # entity-identity assertion. Unimplemented alignments remain unresolved.
    left, right = _np(observed).split(), _np(requested).split()
    method = "literal_counted_np_v1" if left == right else None
    captured = None
    # "the candidate count" abbreviates "the count of candidate <head>": the
    # request's one-word label must be the literal modifier of the counted
    # source nominal ("contains 5 candidate sites"), never a guessed entity.
    if method is None and len(right) == 1 and len(left) == 2 and left[0] == right[0]:
        source = _captured_nominal(source_capture, source_text, source_bounds)
        request = _captured_nominal(request_capture, request_text, request_bounds)
        if (
            source["head"]["pos"] == "NOUN"
            and request["head"]["pos"] in {"ADJ", "NOUN"}
            and request["head"]["dep"] in {"amod", "compound"}
            and request["parent"]["pos"] == "NOUN"
            and (request["parent"]["start"], request["parent"]["end"])
            == request_count_bounds
            and request["parent"]["lemma"] == "count"
            and re.fullmatch("count", request["parent"]["text"], re.I)
        ):
            method = "captured_field_label_to_source_modifier_v1"
            captured = {
                "source": source,
                "request_label": request,
                "meaning": (
                    "literal_count_field_label_modifier_match_not_entity_truth_"
                    "or_NLI_support"
                ),
            }
    if method is None and left and len(left) == len(right) and left[:-1] == right[:-1]:
        if not re.fullmatch(r"[a-z]+", left[-1]) or not re.fullmatch(
            r"[a-z]+", right[-1]
        ):
            return None
        source = _captured_nominal(source_capture, source_text, source_bounds)
        request = _captured_nominal(request_capture, request_text, request_bounds)
        if (
            source["head"]["pos"] == "NOUN"
            and request["head"]["pos"] == "NOUN"
            and source["head"]["lemma"] == request["head"]["lemma"]
            and {source["number"], request["number"]} == {"Sing", "Plur"}
        ):
            method = "captured_common_noun_number_v1"
            captured = {
                "source": source,
                "request": request,
                "meaning": "captured_syntax_not_entity_truth_or_NLI_support",
            }
        elif (
            source["head"]["pos"] == "NOUN"
            and source["number"] == "Plur"
            and source["head"]["lemma"] == request["head"]["text"]
            and request["head"]["pos"] in {"ADJ", "NOUN"}
            and request["head"]["dep"] in {"amod", "compound"}
            and request["parent"]["pos"] == "NOUN"
            and (request["parent"]["start"], request["parent"]["end"])
            == request_count_bounds
            and request["parent"]["lemma"] == "count"
            and re.fullmatch("count", request["parent"]["text"], re.I)
        ):
            method = "captured_field_label_to_source_lemma_v1"
            captured = {
                "source": source,
                "request_label": request,
                "meaning": (
                    "literal_count_field_label_interpretation_not_two_sided_"
                    "noun_inflection_or_entity_truth"
                ),
            }
    if method is None:
        return None
    return {
        "method": method,
        "requested_np": _np(requested),
        "source_np": _np(observed),
        "modifiers": "literal_case_sensitive",
        "lemma_identity": "captured_proposal_only" if captured else "NOT_ASSERTED",
        "captured_alignment": captured,
        "meaning": "closed_literal_count_slot_surface_agreement_only",
    }


def _request(req):
    if req.kind != "quantity" or req.relation != "count" or req.depends_on:
        raise QuantityUnresolved("unsupported_literal_count_request")
    front = re.fullmatch(
        rf"(?:for|in|at|regarding)\s+(?P<scope>[^,?!.]+),\s*what\s+is\s+(?:the\s+)?(?P<unit>{NP})\s+(?P<count>count)[?.!]?",
        req.question.strip(),
        re.I,
    )
    direct = re.fullmatch(
        rf"what\s+is\s+(?:the\s+)?(?P<unit>{NP})\s+(?P<count>count)\s+for\s+(?P<scope>[^,?!.]+)[?.!]?",
        req.question.strip(),
        re.I,
    )
    match = front or direct
    if (
        not match
        or _np(match["scope"]) != _np(req.topic)
        or _attribute(req.attribute) != _attribute(match["unit"] + " count")
    ):
        raise QuantityUnresolved("request_count_attribute_or_scope_unresolved")
    offset = len(req.question) - len(req.question.lstrip())
    return (
        match["unit"],
        (match.start("unit") + offset, match.end("unit") + offset),
        (match.start("count") + offset, match.end("count") + offset),
    )


def _identity(body, identity):
    if (
        type(identity) is not dict
        or not {"document_id", "document_version", "content_hash"} <= identity.keys()
        or identity.keys()
        - {"document_id", "document_version", "content_hash", "workspace_id"}
    ):
        raise QuantityUnresolved("source_identity_schema")
    if (
        type(identity["document_id"]) is not str
        or not identity["document_id"]
        or type(identity["document_version"]) is not int
        or identity["document_version"] < 1
        or identity["content_hash"] != hashlib.sha256(body.encode()).hexdigest()
    ):
        raise QuantityUnresolved("source_identity_mismatch")
    if identity.get("workspace_id") is not None and (
        type(identity["workspace_id"]) is not str or not identity["workspace_id"]
    ):
        raise QuantityUnresolved("source_workspace_unknown")
    return _wire(identity)


def _number(raw):
    integer, _, fraction = raw.partition(".")
    integer = integer.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    return integer + ("." + fraction if fraction else "")


def _typed_mode(profile):
    if profile is None:
        return False
    from app.evidence_policy import recorded_evidence_policy

    policy = recorded_evidence_policy(profile)
    if _wire(policy.record()) != _wire(profile):
        raise ValueError("Canonical quantity evidence profile required")
    return policy.source_governance_profile == "requirement_bound_v1"


def _range_tokens(text, tokens, start, end):
    selected = [t for t in tokens if start <= t["start"] < t["end"] <= end]
    if not selected or selected[0]["start"] != start or selected[-1]["end"] != end:
        raise QuantityUnresolved("source_stated_literal_range_unclosed")
    _nominal_words(text, tokens, {t["i"] for t in selected})
    return selected


def _stated_request(req, use, structure, question):
    """Reconstruct a passive how-many operator, not a context qualification."""
    from app.services.request_parser import validate_capture

    if (
        structure["question"] != question
        or structure["syntax_unresolved"]
        or len(use.units) != 1
        or len(use.scopes) != 1
    ):
        raise QuantityUnresolved("source_stated_request_operator_unresolved")
    tokens = validate_capture(question, structure["original_capture"])["tokens"]
    original, unit, scope = use.original, use.units[0], use.scopes[0]
    if (
        question[original.start : original.end] != original.text
        or original.text != req.original_text
        or (original.start, original.end) != (req.input_start, req.input_end)
        or question[unit.start : unit.end] != unit.text
        or unit.text != req.attribute
        or question[scope.start : scope.end] != scope.text
        or scope.text != req.topic
        or not original.start <= scope.start < scope.end <= original.end
        or not original.start <= unit.start < unit.end <= original.end
        or len(use.head_token_indices) != 1
    ):
        raise QuantityUnresolved("source_stated_request_operator_unresolved")
    unit_tokens = _range_tokens(question, tokens, unit.start, unit.end)
    scope_tokens = _range_tokens(question, tokens, scope.start, scope.end)
    head, predicate = unit_tokens[-1], tokens[use.head_token_indices[0]]
    many = [
        tokens[i] for i in head["children"] if tokens[i]["text"].casefold() == "many"
    ]
    aux = [tokens[i] for i in predicate["children"] if tokens[i]["dep"] == "auxpass"]
    if (
        predicate["pos"] != "VERB"
        or predicate["text"].casefold() != req.relation
        or "VerbForm=Part" not in predicate["morph"].split("|")
        or head["pos"] != "NOUN"
        or head["dep"] != "nsubjpass"
        or head["head"] != predicate["i"]
        or len(many) != 1
        or many[0]["dep"] != "amod"
        or len(aux) != 1
        or aux[0]["lemma"] != "be"
        or "Tense=Pres" not in aux[0]["morph"].split("|")
    ):
        raise QuantityUnresolved("source_stated_request_operator_unresolved")
    how = [
        tokens[i]
        for i in many[0]["children"]
        if tokens[i]["text"].casefold() == "how" and tokens[i]["dep"] == "advmod"
    ]
    prep = [
        t
        for t in tokens
        if t["head"] == predicate["i"]
        and t["dep"] == "prep"
        and t["text"].casefold() == "for"
    ]
    if len(how) != 1 or len(prep) != 1 or scope_tokens[-1]["head"] != prep[0]["i"]:
        raise QuantityUnresolved("source_stated_request_operator_unresolved")
    ids = {
        t["i"]
        for t in unit_tokens + scope_tokens + many + how + aux + prep + [predicate]
    }
    actual = {
        t["i"]
        for t in tokens
        if original.start <= t["start"] < t["end"] <= original.end
    }
    punctuation = {
        i for i in actual if tokens[i]["dep"] == "punct" and tokens[i]["text"] == ","
    }
    if actual != ids | punctuation:
        raise QuantityUnresolved("source_stated_request_operator_unresolved")
    words = [t for t in unit_tokens if t["pos"] != "PUNCT"]
    return {
        "contract": "captured-passive-quantity-operator-v1",
        "original": _literal(question, original.start, original.end),
        "requested_unit": _literal(question, unit.start, unit.end),
        "unit_words": words,
        "unit_head": head,
        "predicate": predicate,
        "scope": _literal(question, scope.start, scope.end),
        "meaning": "captured_request_operator_not_source_support",
    }


def _stated_target(req, body, tokens, head):
    owned, todo = set(), [head]
    while todo:
        index = todo.pop()
        if index in owned:
            raise QuantityUnresolved("source_stated_target_cycle")
        owned.add(index)
        for child in tokens[index]["children"]:
            if tokens[child]["dep"] not in {
                "compound",
                "nmod",
                "amod",
                "advmod",
                "punct",
                "det",
            }:
                raise QuantityUnresolved(
                    "source_stated_target_qualification_unresolved"
                )
            todo.append(child)
    _nominal_words(body, tokens, owned)
    left, right = (
        min(tokens[i]["start"] for i in owned),
        max(tokens[i]["end"] for i in owned),
    )
    literal = body[left:right]
    if literal != req.topic:
        first = tokens[min(owned)]
        if (
            first["dep"] != "det"
            or first["head"] != head
            or first["text"].casefold() not in {"a", "an", "the"}
            or body[first["end"] : right].strip() != req.topic
        ):
            raise QuantityUnresolved("source_stated_whole_literal_target_mismatch")
    return owned, _literal(body, left, right)


def _stated_unit(tokens, head, body, operator):
    owned = _qualified_nominal(tokens, head, numeric=True)
    words = _nominal_words(body, tokens, owned)
    source_head, asked_head = tokens[head], operator["unit_head"]

    def noun_number(token):
        return dict(
            part.split("=", 1) for part in token["morph"].split("|") if "=" in part
        ).get("Number")

    if (
        not words
        or words[-1]["i"] != head
        or source_head["pos"] != "NOUN"
        or source_head["lemma"] != asked_head["lemma"]
        or noun_number(source_head) not in {"Sing", "Plur"}
        or noun_number(asked_head) not in {"Sing", "Plur"}
    ):
        raise QuantityUnresolved("source_stated_requested_unit_mismatch")
    asked = [t["text"] for t in operator["unit_words"][:-1]]
    observed = iter(t["text"] for t in words[:-1])
    if any(not any(value == word for value in observed) for word in asked):
        raise QuantityUnresolved("source_stated_requested_modifier_mismatch")
    number = [i for i in owned if tokens[i]["dep"] == "nummod"]
    if (
        len(number) != 1
        or number[0] != min(owned)
        or not re.fullmatch(NUMBER, tokens[number[0]]["text"])
    ):
        raise QuantityUnresolved("source_stated_number_unresolved")
    return owned, number[0]


def _stated_clause(req, body, annotation, sentence, operator):
    tokens = annotation["tokens"]
    indices = set(range(sentence["token_start"], sentence["token_end"]))
    roots = [tokens[i] for i in indices if tokens[i]["dep"] == "ROOT"]
    if (
        len(roots) != 1
        or roots[0]["pos"] != "VERB"
        or roots[0]["lemma"] != operator["predicate"]["lemma"]
        or "Tense=Pres" not in roots[0]["morph"].split("|")
    ):
        raise QuantityUnresolved("source_stated_requested_predicate_mismatch")
    root = roots[0]
    subjects = [i for i in root["children"] if tokens[i]["dep"] == "nsubj"]
    objects = [i for i in root["children"] if tokens[i]["dep"] in {"obj", "dobj"}]
    if len(subjects) != 1 or len(objects) != 1:
        raise QuantityUnresolved("source_stated_arguments_unresolved")
    subject, subject_range = _stated_target(req, body, tokens, subjects[0])
    amount, number = _stated_unit(tokens, objects[0], body, operator)
    punctuation = {
        i
        for i in indices
        if tokens[i]["dep"] == "punct" and tokens[i]["head"] == root["i"]
    }
    if indices != subject | amount | punctuation | {root["i"]}:
        raise QuantityUnresolved("source_stated_clause_has_unconsumed_material")

    def span(ids):
        return _literal(
            body,
            min(tokens[i]["start"] for i in ids),
            max(tokens[i]["end"] for i in ids),
        )

    return {
        "source_clause": _literal(body, sentence["start"], sentence["end"]),
        "source_subject": subject_range,
        "source_relation": _literal(body, root["start"], root["end"]),
        "number": span({number}),
        "amount": span(amount),
        "declared_counted_np": span(amount - {number}),
        "actual_target": _literal(
            body, subject_range["end"] - len(req.topic), subject_range["end"]
        ),
    }


def _stated_plan_record(plan):
    """Use the existing context's delegated record, never invented plan fields."""
    from app.services.captured_answer_planning import CapturedAnswerContext
    from app.services.captured_plan_binding import CapturedRequestPlan

    if isinstance(plan, CapturedAnswerContext):
        if not isinstance(plan.plan, CapturedRequestPlan):
            raise QuantityUnresolved("source_stated_context_plan_invalid")
        record = plan.record()
        if record != plan.plan.record():
            raise QuantityUnresolved("source_stated_context_record_differs")
        return record
    if not isinstance(plan, CapturedRequestPlan):
        raise QuantityUnresolved("source_stated_plan_transport_invalid")
    return plan.record()


def _stated_cover(req, plan, operator):
    from app.services.request_parser import validate_capture

    original = json.loads(_stated_plan_record(plan)["source_productions_json"])[
        "original_inputs"
    ]
    fields = []
    for snapshot in original["snapshots"]:
        body = snapshot["body"]
        if req.topic not in body:
            continue
        retained = [
            r
            for r in original["source_captures"]
            if r["identity"] == snapshot["identity"]
        ]
        if len(retained) != 1 or len(retained[0]["windows"]) != 1:
            raise QuantityUnresolved("source_stated_full_field_scan_unavailable")
        window = retained[0]["windows"][0]
        if window["start"] != 0 or window["end"] != len(body):
            raise QuantityUnresolved("source_stated_full_field_scan_unavailable")
        annotation = validate_capture(body, json.loads(window["capture_json"]))
        for sentence in annotation["sentences"]:
            tokens = annotation["tokens"][
                sentence["token_start"] : sentence["token_end"]
            ]
            units = [t for t in tokens if t["lemma"] == operator["unit_head"]["lemma"]]
            text = body[sentence["start"] : sentence["end"]]
            if re.search(r"\b(?:read|consult|see|follow|according)\b", text, re.I) and (
                units
                or re.search(
                    r"\b(?:count|quantity|instructions|appendix)\b", text, re.I
                )
            ):
                raise QuantityUnresolved("source_stated_potential_required_reference")
            if units and (
                any(t["dep"] == "nummod" for t in tokens)
                or any(t["lemma"] == operator["predicate"]["lemma"] for t in tokens)
            ):
                metadata = json.loads(snapshot["metadata_json"])
                if any(
                    metadata.get(key) is not None
                    for key in ("condition", "conflict_group")
                ):
                    raise QuantityUnresolved(
                        "source_stated_curated_condition_unresolved"
                    )
                field = _stated_clause(req, body, annotation, sentence, operator)
                fields.append({"identity": snapshot["identity"], "field": field})
    if len(fields) != 1:
        raise QuantityUnresolved("source_stated_ambiguous_or_missing_field")
    return fields


def _stated_field_and_cover(req, body, start, end, captured, plan, use, request):
    from app.services.request_parser import validate_capture

    operator = _stated_request(
        req,
        use,
        {
            "question": plan.question,
            "syntax_unresolved": [],
            "original_capture": request,
        },
        plan.question,
    )
    annotation = validate_capture(body, captured)
    sentences = [
        s for s in annotation["sentences"] if s["start"] <= start < end <= s["end"]
    ]
    if len(sentences) != 1:
        raise QuantityUnresolved("source_stated_selected_clause_unresolved")
    field = _stated_clause(req, body, annotation, sentences[0], operator)
    if (start, end) not in {
        (field[key]["start"], field[key]["end"]) for key in ("number", "amount")
    }:
        raise QuantityUnresolved("raw_span_not_exact_bound_amount_or_number")
    cover = _stated_cover(req, plan, operator)
    if (
        cover[0]["field"] != field
        or cover[0]["identity"]["content_hash"]
        != hashlib.sha256(body.encode()).hexdigest()
    ):
        raise QuantityUnresolved("source_stated_selected_field_differs")
    return {
        **field,
        "source_stated_scope": {
            "contract": "source-stated-qualified-quantity-scope-v1",
            "request_operator": operator,
            "field_cover": cover,
            "field_cover_scope": "ALL_RETAINED_EXACT_LITERAL_TARGET_DOCUMENTS",
            "implicit_alias_absence": "NOT_ESTABLISHED",
            "unqualified_total": "NOT_ASSERTED",
            "aggregation": "NOT_ASSERTED",
            "publication_value": "COMPLETE_LITERAL_SOURCE_CLAUSE",
            "NI": "REQUIRED_SEPARATELY",
        },
    }


def _typed_request(req, profile, plan):
    if not _typed_mode(profile) or plan is None or req.kind != "quantity":
        raise QuantityUnresolved("typed_count_requires_canonical_profile_and_plan")
    if profile.get("procedure_scope_profile") in {
        "activity_quote_v1",
        "activity_quote_v2",
    }:
        from app.services.captured_answer_planning import CapturedAnswerContext

        if isinstance(plan, CapturedAnswerContext):
            _stated_plan_record(plan)
    record = plan.record()
    uses = [u for u in plan.uses if u.requirement_id == req.id]
    if (
        record.get("contract") != "staged-request-plan-v2"
        or json.loads(record["evidence_profile_json"]) != profile
        or req not in plan.requirements
        or len(uses) != 1
    ):
        raise QuantityUnresolved("typed_count_request_does_not_reconstruct")
    use = uses[0]
    stated = None
    if use.units and profile.get("procedure_scope_profile") in {
        "activity_quote_v1",
        "activity_quote_v2",
    }:
        stated = _stated_request(
            req, use, json.loads(record["structure_json"]), plan.question
        )
    references = use.references or []
    scope_resolved = len(use.scopes or []) == 1 and all(
        (ref.text or "").casefold() in _QUANTITY_PRONOUNS for ref in references
    )
    if (
        req.depends_on
        or (references and not scope_resolved)
        or any(
            getattr(use, key)
            for key in (
                "conditions",
                "condition_ast",
                "modality",
                "governors",
                "quantifiers",
                "negation",
                "execution_dependencies",
            )
        )
    ):
        raise QuantityUnresolved("typed_count_request_qualification_unresolved")
    if use.units and stated is None:
        raise QuantityUnresolved("typed_count_request_qualification_unresolved")
    structure = json.loads(record["structure_json"])
    features = json.loads(use.features_json)
    if (
        structure["syntax_unresolved"]
        or not req.topic
        or not req.attribute
        or (features.get("attribute") != req.attribute)
    ):
        raise QuantityUnresolved("typed_count_request_attribute_or_syntax_unresolved")
    from app.services.request_parser import validate_capture

    capture = structure["original_capture"]
    validate_capture(structure["question"], capture)
    return record, use, capture


def typed_quantity_source(req, context, *, evidence_profile, request_plan):
    """Find only exact retained source/chunk material for an initial candidate."""
    record, _, _ = _typed_request(req, evidence_profile, request_plan)
    original = json.loads(record["source_productions_json"])["original_inputs"]
    matches = []
    for snapshot in original["snapshots"]:
        body = snapshot["body"]
        if context != body and not any(
            c["literal"]["text"] == context for c in snapshot["chunks"]
        ):
            continue
        start = body.find(context)
        if start >= 0 and body.find(context, start + 1) < 0:
            identity = {
                k: v for k, v in snapshot["identity"].items() if k != "snapshot_id"
            }
            matches.append((body, identity, start))
    if len(matches) != 1:
        raise QuantityUnresolved(
            "typed_count_source_membership_or_projection_unresolved"
        )
    return matches[0]


def _typed_capture(req, body, identity, profile, plan, request_capture, source_capture):
    record, use, original_request = _typed_request(req, profile, plan)
    original = json.loads(record["source_productions_json"])["original_inputs"]
    snapshots = [
        s
        for s in original["snapshots"]
        if s["body"] == body
        and all(s["identity"].get(k) == v for k, v in identity.items())
    ]
    if len(snapshots) != 1:
        raise QuantityUnresolved("typed_count_authoritative_source_not_in_plan")
    rows = [
        c
        for c in original["source_captures"]
        if c["identity"] == snapshots[0]["identity"]
    ]
    if len(rows) != 1 or len(rows[0]["windows"]) != 1:
        raise QuantityUnresolved("typed_count_full_capture_window_required")
    window = rows[0]["windows"][0]
    if window["start"] != 0 or window["end"] != len(body):
        raise QuantityUnresolved("typed_count_full_capture_window_required")
    original_source = json.loads(window["capture_json"])
    if request_capture is not None and _wire(request_capture) != _wire(
        original_request
    ):
        raise ValueError("Typed count original request capture differs")
    if source_capture is not None and _wire(source_capture) != _wire(original_source):
        raise ValueError("Typed count original source capture differs")
    return use, original_request, original_source, snapshots[0]["identity"]


def _count_nominal(tokens, head, *, numeric=False):
    owned, todo = set(), [head]
    while todo:
        index = todo.pop()
        token = tokens[index]
        if index in owned:
            raise QuantityUnresolved("typed_count_nominal_cycle")
        owned.add(index)
        for child in token["children"]:
            item = tokens[child]
            allowed = item["dep"] == "compound" and item["pos"] in {"NOUN", "PROPN"}
            allowed |= item["dep"] == "det" and item["text"].casefold() in {
                "a",
                "an",
                "the",
            }
            allowed |= numeric and item["dep"] == "nummod" and item["pos"] == "NUM"
            if not allowed:
                raise QuantityUnresolved("typed_count_nominal_qualification_unresolved")
            todo.append(child)
    return owned


def _qualified_nominal(tokens, head, *, numeric=False):
    """Retain a closed nominal proposal; matching its requested words is separate."""
    owned, todo = set(), [head]
    while todo:
        index = todo.pop()
        if index in owned:
            raise QuantityUnresolved("typed_count_nominal_cycle")
        owned.add(index)
        for child in tokens[index]["children"]:
            item = tokens[child]
            allowed = item["dep"] in {"compound", "amod"} and item["pos"] in {
                "NOUN",
                "PROPN",
                "ADJ",
            }
            allowed |= numeric and item["dep"] == "nummod" and item["pos"] == "NUM"
            allowed |= item["dep"] == "punct" and item["text"] == "-"
            if not allowed:
                raise QuantityUnresolved("typed_count_nominal_qualification_unresolved")
            todo.append(child)
    return owned


def _nominal_words(text, tokens, owned):
    ordered = sorted(owned)
    words = []
    for position, index in enumerate(ordered):
        token = tokens[index]
        if token["pos"] == "PUNCT":
            if (
                token["text"] != "-"
                or position == 0
                or position == len(ordered) - 1
                or tokens[ordered[position - 1]]["end"] != token["start"]
                or token["end"] != tokens[ordered[position + 1]]["start"]
            ):
                raise QuantityUnresolved("typed_count_nominal_hyphen_unclosed")
        elif token["dep"] != "nummod":
            words.append(token)
        if (
            position
            and text[tokens[ordered[position - 1]]["end"] : token["start"]].strip()
        ):
            raise QuantityUnresolved("typed_count_nominal_range_unclosed")
    return words


def _requested_qualified_nominal(req, use, question, capture):
    from app.services.request_parser import validate_capture

    tokens = validate_capture(question, capture)["tokens"]
    if question[use.original.start : use.original.end] != use.original.text:
        raise QuantityUnresolved("typed_count_original_request_range_unclosed")
    matches = [
        m
        for m in re.finditer(re.escape(req.attribute), question)
        if use.original.start <= m.start() < m.end() <= use.original.end
    ]
    if len(matches) != 1:
        raise QuantityUnresolved("typed_count_requested_nominal_unclosed")
    start, end = matches[0].span()
    attribute = [t for t in tokens if start <= t["start"] < t["end"] <= end]
    if not attribute or attribute[0]["start"] != start or attribute[-1]["end"] != end:
        raise QuantityUnresolved("typed_count_requested_nominal_unclosed")
    payload = [
        t
        for t in attribute[:-1]
        if t["pos"] != "PUNCT"
        and not (t["dep"] == "det" and t["text"].casefold() in {"a", "an", "the"})
    ]
    if len(payload) < 2:
        raise QuantityUnresolved("typed_count_requested_qualifier_missing")
    field = attribute[-1]
    heads = [
        t
        for t in attribute
        if t["head"] == field["i"] and t["dep"] == "compound" and t["pos"] == "NOUN"
    ]
    if (
        field["i"] not in use.head_token_indices
        or field["lemma"] != "quantity"
        or len(heads) != 1
    ):
        raise QuantityUnresolved("typed_count_requested_nominal_unclosed")
    head = heads[0]
    owned = _qualified_nominal(tokens, head["i"])
    determiners = {
        t["i"]
        for t in attribute
        if t["dep"] == "det"
        and t["head"] == field["i"]
        and t["text"].casefold() in {"a", "an", "the"}
    }
    if {t["i"] for t in attribute} != owned | determiners | {field["i"]}:
        raise QuantityUnresolved("typed_count_requested_nominal_unclosed")
    words = _nominal_words(question, tokens, owned)
    if len(words) < 2 or words[-1]["i"] != head["i"]:
        raise QuantityUnresolved("typed_count_requested_qualifier_missing")
    return tokens, owned, head, words


def _bound_qualified_amount(req, body, tokens, head, request_context):
    if request_context is None:
        raise QuantityUnresolved("typed_count_nominal_qualification_unresolved")
    use, question, capture = request_context
    request_tokens, request_ids, request_head, requested = _requested_qualified_nominal(
        req, use, question, capture
    )
    owned = _qualified_nominal(tokens, head, numeric=True)
    observed = _nominal_words(body, tokens, owned)
    actual_head = tokens[head]

    def numbers(token):
        return dict(
            part.split("=", 1) for part in token["morph"].split("|") if "=" in part
        ).get("Number")

    if (
        len(observed) != len(requested)
        or observed[-1]["i"] != head
        or [t["text"] for t in observed[:-1]] != [t["text"] for t in requested[:-1]]
        or actual_head["pos"] != request_head["pos"]
        or actual_head["pos"] != "NOUN"
        or actual_head["lemma"] != request_head["lemma"]
        or not (
            actual_head["text"] == request_head["text"]
            or {numbers(actual_head), numbers(request_head)} == {"Sing", "Plur"}
        )
    ):
        raise QuantityUnresolved("typed_count_requested_qualified_unit_mismatch")
    unit_ids = {i for i in owned if tokens[i]["dep"] != "nummod"}

    def literal(text, items, ids):
        return _literal(
            text, min(items[i]["start"] for i in ids), max(items[i]["end"] for i in ids)
        )

    return owned, {
        "method": "captured_requested_qualified_count_np_v1",
        "requested_np": literal(question, request_tokens, request_ids),
        "source_np": literal(body, tokens, unit_ids),
        "request_tokens": [request_tokens[i] for i in sorted(request_ids)],
        "source_tokens": [tokens[i] for i in sorted(unit_ids)],
        "meaning": "literal_requested_modifiers_and_captured_noun_number_only_not_NLI",
    }


def _typed_amount(req, body, tokens, head, request_context):
    if request_context is not None:
        try:
            _requested_qualified_nominal(req, *request_context)
        except QuantityUnresolved as exc:
            if str(exc) != "typed_count_requested_qualifier_missing":
                raise
        else:
            return _bound_qualified_amount(req, body, tokens, head, request_context)
    return _count_nominal(tokens, head, numeric=True), None


def _typed_field(req, body, start, end, capture, *, request_context=None):
    from app.services.request_parser import validate_capture
    from app.services.requirement_quantities import _CONTAINER_REQUESTS

    annotation = validate_capture(body, capture)
    tokens = annotation["tokens"]
    sentences = [
        s for s in annotation["sentences"] if s["start"] <= start < end <= s["end"]
    ]
    if len(sentences) != 1:
        raise QuantityUnresolved("typed_count_selected_clause_unresolved")
    sentence = sentences[0]
    indices = set(range(sentence["token_start"], sentence["token_end"]))
    roots = [tokens[i] for i in indices if tokens[i]["dep"] == "ROOT"]
    if (
        len(roots) != 1
        or roots[0]["lemma"] not in _CONTAINER_REQUESTS
        or roots[0]["pos"] != "VERB"
        or "Tense=Pres" not in roots[0]["morph"].split("|")
    ):
        raise QuantityUnresolved("typed_count_containment_relation_unresolved")
    root = roots[0]
    subjects = [i for i in root["children"] if tokens[i]["dep"] == "nsubj"]
    objects = [i for i in root["children"] if tokens[i]["dep"] in {"obj", "dobj"}]
    if len(subjects) != 1 or len(objects) != 1 or tokens[objects[0]]["pos"] != "NOUN":
        raise QuantityUnresolved("typed_count_subject_or_count_noun_unresolved")
    subject = _count_nominal(tokens, subjects[0])
    amount, alignment = _typed_amount(req, body, tokens, objects[0], request_context)
    punctuation = {
        i
        for i in indices
        if tokens[i]["dep"] == "punct" and tokens[i]["head"] == root["i"]
    }
    if indices != subject | amount | punctuation | {root["i"]}:
        raise QuantityUnresolved("typed_count_clause_has_unconsumed_material")
    numbers = [i for i in amount if tokens[i]["dep"] == "nummod"]
    if (
        len(numbers) != 1
        or numbers[0] != min(amount)
        or not re.fullmatch(NUMBER, tokens[numbers[0]]["text"])
    ):
        raise QuantityUnresolved("typed_count_number_unresolved")
    unit = amount - set(numbers)

    def span(ids):
        return _literal(
            body,
            min(tokens[i]["start"] for i in ids),
            max(tokens[i]["end"] for i in ids),
        )

    subject_range, unit_range, number_range, amount_range = (
        span(subject),
        span(unit),
        span(set(numbers)),
        span(amount),
    )
    if (start, end) not in {
        (number_range["start"], number_range["end"]),
        (amount_range["start"], amount_range["end"]),
    }:
        raise QuantityUnresolved("raw_span_not_exact_bound_amount_or_number")
    target = re.search(r"\b" + re.escape(req.topic) + r"\b", subject_range["text"])
    if target is None:
        raise QuantityUnresolved("typed_count_literal_source_scope_unresolved")
    return {
        **({"counted_np_alignment": alignment} if alignment is not None else {}),
        "source_clause": _literal(body, sentence["start"], sentence["end"]),
        "source_subject": subject_range,
        "source_relation": _literal(body, root["start"], root["end"]),
        "number": number_range,
        "amount": amount_range,
        "declared_counted_np": unit_range,
        "actual_target": _literal(
            body,
            subject_range["start"] + target.start(),
            subject_range["start"] + target.end(),
        ),
    }


def _compile_typed_count(
    req, body, start, end, identity, profile, plan, request_capture, source_capture
):
    identity = _identity(body, identity)
    use, request, captured, snapshot_identity = _typed_capture(
        req, body, identity, profile, plan, request_capture, source_capture
    )
    field = (
        _stated_field_and_cover(req, body, start, end, captured, plan, use, request)
        if use.units
        else _typed_field(
            req,
            body,
            start,
            end,
            captured,
            request_context=(use, plan.question, request),
        )
    )
    canonical_field = {
        "request_requirement_sha256": _hash(_wire(asdict(req))),
        "requirement_id": req.id,
        "requested_target": req.topic,
        "requested_attribute": req.attribute,
        "request_relation": req.relation,
        "request_use": asdict(use),
        "immutable_field_source": identity,
        "source_snapshot_identity": snapshot_identity,
        "source_clause": field["source_clause"],
        "source_subject": field["source_subject"],
        "source_relation": field["source_relation"],
        "counted_np_range": field["declared_counted_np"],
        "number_range": field["number"],
        "conditions": [],
        "modality": [],
        "negation": False,
    }
    if "counted_np_alignment" in field:
        canonical_field["counted_np_alignment"] = field["counted_np_alignment"]
    if "source_stated_scope" in field:
        canonical_field["source_stated_scope"] = field["source_stated_scope"]
    value = {
        "number": _number(field["number"]["text"]),
        "unit": field["declared_counted_np"]["text"],
    }
    return _wire(
        dict(
            contract=CONTRACT,
            method=STATED_METHOD if use.units else TYPED_METHOD,
            request_requirement=asdict(req),
            source_identity=identity,
            whole_source=_literal(body, 0, len(body)),
            raw_value=_literal(body, start, end),
            **field,
            canonical_field=canonical_field,
            canonical_value=value,
            value_identity=_hash({"field": canonical_field, "value": value}),
            request_capture_sha256=request["capture_sha256"],
            source_capture_sha256=captured["capture_sha256"],
            model_support="NOT_ASSERTED",
            requested_attribute_source_relation_NLI="REQUIRED_SEPARATELY",
            source_authority_and_currentness="REQUIRED_SEPARATELY",
            external_source_context_and_conditions="REQUIRED_SEPARATELY_NOT_ABSENCE_PROOF",
        )
    )


_LITERAL_COUNT_PATTERNS = [
    (
        "assigned_to",
        rf"\s*There\s+(?:are|is)\s+(?P<number>{NUMBER})\s+(?P<unit>{NP})\s+assigned\s+to\s+(?P<scope>[^.!?\n]+?)\s*[.]?\s*",
    ),
    (
        "declared_count_for",
        rf"\s*(?:The\s+)?(?P<field>{NP})\s+count\s+for\s+(?P<scope>[^.!?\n]+?)\s+is\s+(?P<number>{NUMBER})(?:\s+(?P<unit>{NP}))?\s*[.]?\s*",
    ),
    (
        "declared_container",
        rf"\s*(?:A|An|The)\s+(?P<scope>{NP})\s+(?:contains?|has|uses?|holds?|carries|includes?)\s+(?:a\s+)?(?P<number>{NUMBER})\s+(?P<unit>{NP})\s*[.]?\s*",
    ),
]


def _literal_alignments(groups, unit, declared_unit, unit_field, match, left, options):
    declared_alignment = _unit_alignment(
        declared_unit,
        unit,
        source_bounds=(
            match.start(unit_field) + left,
            match.end(unit_field) + left,
        ),
        **options,
    )
    amount_alignment = (
        _unit_alignment(
            groups["unit"],
            unit,
            source_bounds=(match.start("unit") + left, match.end("unit") + left),
            **options,
        )
        if groups.get("unit")
        else None
    )
    if declared_alignment is None:
        raise QuantityUnresolved("source_counted_np_mismatch")
    if groups.get("unit") and amount_alignment is None:
        raise QuantityUnresolved("selected_quantity_unit_mismatch")
    return declared_alignment, amount_alignment


def _literal_count_field(req, body, start, end, unit, options):
    # The literal relations bind one closed clause: the sentence containing the
    # proposed value, never an unrelated number elsewhere in the source.
    left = 0
    for i in range(start - 1, -1, -1):
        if body[i] in ".!?\n":
            left = i + 1
            break
    right = len(body)
    for i in range(end, len(body)):
        if body[i] == "\n":
            right = i
            break
        if body[i] in ".!?":
            right = i + 1
            break
    clause = body[left:right]
    matches = [
        (relation, match)
        for relation, pattern in _LITERAL_COUNT_PATTERNS
        if (match := re.fullmatch(pattern, clause, re.I))
    ]
    if len(matches) != 1:
        raise QuantityUnresolved("whole_literal_count_relation_unresolved")
    relation, match = matches[0]
    if _np(match["scope"]) != _np(req.topic):
        raise QuantityUnresolved("source_count_target_mismatch")
    groups = match.groupdict()
    declared_unit = groups.get("field") or groups.get("unit")
    unit_field = "field" if groups.get("field") else "unit"
    declared_alignment, amount_alignment = _literal_alignments(
        groups, unit, declared_unit, unit_field, match, left, options
    )
    number = (match.start("number") + left, match.end("number") + left)
    amount = number if not groups.get("unit") else (number[0], match.end("unit") + left)
    if (start, end) not in {number, amount}:
        raise QuantityUnresolved("raw_span_not_exact_bound_amount_or_number")
    unit_range = (
        match.start(unit_field) + left,
        match.end(unit_field) + left,
    )
    scope = (match.start("scope") + left, match.end("scope") + left)
    return (
        relation,
        number,
        amount,
        unit_range,
        scope,
        declared_alignment,
        amount_alignment,
    )


def compile_quantity_binding(
    req,
    body,
    start,
    end,
    *,
    source_identity,
    request_capture=None,
    source_capture=None,
    evidence_profile=None,
    request_plan=None,
):
    if type(body) is not str or not body.strip() or len(body) > 8192:
        raise QuantityUnresolved("whole_quantity_body_budget_or_empty")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(body)
    ):
        raise QuantityUnresolved("raw_quantity_range_invalid")
    if req.relation != "count" and _typed_mode(evidence_profile):
        return _compile_typed_count(
            req,
            body,
            start,
            end,
            source_identity,
            evidence_profile,
            request_plan,
            request_capture,
            source_capture,
        )
    unit, request_unit_bounds, request_count_bounds = _request(req)
    identity = _identity(body, source_identity)
    if (
        req.source_workspace is not None
        and identity.get("workspace_id") != req.source_workspace
    ):
        raise QuantityUnresolved("requested_source_workspace_mismatch")
    (
        relation,
        number,
        amount,
        unit_range,
        scope,
        declared_alignment,
        amount_alignment,
    ) = _literal_count_field(
        req,
        body,
        start,
        end,
        unit,
        {
            "request_capture": request_capture,
            "source_capture": source_capture,
            "request_text": req.question,
            "source_text": body,
            "request_bounds": request_unit_bounds,
            "request_count_bounds": request_count_bounds,
        },
    )
    alignment = {"declared": declared_alignment, "amount": amount_alignment}
    field = {
        "request_requirement_sha256": _hash(_wire(asdict(req))),
        "requirement_id": req.id,
        "requested_target": _np(req.topic),
        "counted_np": _np(unit),
        "request_relation": req.relation,
        "source_relation": relation,
        "source_workspace": identity.get("workspace_id"),
        # Equality is deliberately limited to this exact immutable occurrence.
        # Distinct sources/versions may have different external governing context.
        "immutable_field_source": identity,
        "number_range": list(number),
        "counted_np_range": list(unit_range),
        "conditions": [],
        "negation": False,
        "modality": [],
    }
    value = {
        "number": _number(body[number[0] : number[1]]),
        "unit": _np(unit),
    }
    return _wire(
        {
            "contract": CONTRACT,
            "method": METHOD,
            "request_requirement": asdict(req),
            "source_identity": identity,
            "whole_source": _literal(body, 0, len(body)),
            "raw_value": _literal(body, start, end),
            "number": _literal(body, *number),
            "amount": _literal(body, *amount),
            "declared_counted_np": _literal(body, *unit_range),
            "counted_np_alignment": alignment,
            "actual_target": _literal(body, *scope),
            "canonical_field": field,
            "canonical_value": value,
            "value_identity": _hash({"field": field, "value": value}),
            "model_support": "NOT_ASSERTED",
            "source_authority_and_whole_source_nli": "REQUIRED_SEPARATELY",
            "external_source_context_and_conditions": (
                "REQUIRED_SEPARATELY_NOT_ABSENCE_PROOF"
            ),
            "meaning": (
                "bounded_literal_field_binding_not_entity_truth_or_universal_grammar"
            ),
        }
    )


def reconstruct_quantity_binding(
    record,
    req,
    body,
    start,
    end,
    *,
    source_identity,
    request_capture=None,
    source_capture=None,
    evidence_profile=None,
    request_plan=None,
):
    rebuilt = compile_quantity_binding(
        req,
        body,
        start,
        end,
        source_identity=source_identity,
        request_capture=request_capture,
        source_capture=source_capture,
        evidence_profile=evidence_profile,
        request_plan=request_plan,
    )
    if _hash(record) != _hash(rebuilt):
        raise QuantityUnresolved("recorded_quantity_binding_does_not_reconstruct")
    return rebuilt


def quantity_value_identity(
    record,
    req,
    body,
    start,
    end,
    *,
    source_identity,
    request_capture=None,
    source_capture=None,
    evidence_profile=None,
    request_plan=None,
):
    # No public raw-string normalization can grant this identity.
    return reconstruct_quantity_binding(
        record,
        req,
        body,
        start,
        end,
        source_identity=source_identity,
        request_capture=request_capture,
        source_capture=source_capture,
        evidence_profile=evidence_profile,
        request_plan=request_plan,
    )["value_identity"]


def produce_quantity_candidate(
    req,
    body,
    *,
    source_identity,
    chunk_content,
    chunk_start,
    raw_start,
    raw_end,
    request_capture=None,
    source_capture=None,
    evidence_profile=None,
    request_plan=None,
):
    """Producer adapter: immutable projection and field binding precede NLI.

    Root resolves/authenticates the source. This function never selects a value,
    runs a model, or accepts support. The claim keeps local chunk coordinates.
    """
    if (
        type(chunk_content) is not str
        or type(chunk_start) is not int
        or chunk_start < 0
        or body[chunk_start : chunk_start + len(chunk_content)] != chunk_content
    ):
        raise QuantityUnresolved("literal_chunk_to_body_projection_invalid")
    if (
        type(raw_start) is not int
        or type(raw_end) is not int
        or not 0 <= raw_start < raw_end <= len(chunk_content)
    ):
        raise QuantityUnresolved("raw_chunk_range_invalid")
    proof = compile_quantity_binding(
        req,
        body,
        chunk_start + raw_start,
        chunk_start + raw_end,
        source_identity=source_identity,
        request_capture=request_capture,
        source_capture=source_capture,
        evidence_profile=evidence_profile,
        request_plan=request_plan,
    )
    from app.services.linguistic_quantities import (
        _typed_count_claim,
        scoped_quantity_claim,
    )

    claim = (
        _typed_count_claim(req, proof, chunk_content, chunk_start)
        if proof["method"] in {TYPED_METHOD, STATED_METHOD}
        else scoped_quantity_claim(req, chunk_content, raw_start, raw_end)
    )
    if claim.rejection or not claim.hypothesis:
        raise QuantityUnresolved(
            "local_claim_still_unresolved_after_literal_field_binding"
        )
    if claim.value != chunk_content[claim.start : claim.end]:
        raise QuantityUnresolved("claim_is_not_literal_source")
    return claim, proof


def consume_quantity_candidate(
    record,
    req,
    body,
    *,
    source_identity,
    chunk_content,
    chunk_start,
    raw_start,
    raw_end,
    request_capture=None,
    source_capture=None,
    evidence_profile=None,
    request_plan=None,
):
    """Rebuild from caller's real source/chunk/request, never a success flag."""
    claim, rebuilt = produce_quantity_candidate(
        req,
        body,
        source_identity=source_identity,
        chunk_content=chunk_content,
        chunk_start=chunk_start,
        raw_start=raw_start,
        raw_end=raw_end,
        request_capture=request_capture,
        source_capture=source_capture,
        evidence_profile=evidence_profile,
        request_plan=request_plan,
    )
    if _hash(record) != _hash(rebuilt):
        raise QuantityUnresolved("recorded_quantity_binding_does_not_reconstruct")
    return claim, rebuilt
