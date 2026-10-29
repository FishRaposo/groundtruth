"""Pinned lexical risk candidates bound to actual source predicate occurrences.

Possible senses veto ordinary interpretation; they never establish actual sense,
entity facts, required-reference presence, or universal implicit-reference absence.
VerbNet 3.X Copyright 2009 University of Colorado; see data/VERBNET_LICENSE.txt.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from importlib import resources
from typing import Any

CONTRACT = "possible-content-sense-guard-v1"
PAYLOAD_SHA256 = "928bab0717a3a37d54074de4ea811bc38831b1f1b9e72fb4bccf50b7b58a266c"
LICENSE_SHA256 = "6a28570a960b693eb96800264ff1379eb374436dec6211b23b516e54b6e2f13f"
SOURCE_COMMIT = "ae8e9cfdc2c0d3414b748763612f1a0a34194cc1"
MAX_FRAME_CANDIDATES = 512
_ACTORS = frozenset({"Agent", "Actor"})
_CONTENT_PREDICATES = frozenset({"act", "perform", "abide_by"})
_SUBJECTS = frozenset({"nsubj", "nsubjpass", "csubj", "csubjpass"})
_OBJECTS = frozenset({"dobj", "obj", "iobj", "dative", "attr", "oprd"})
_CLAUSES = frozenset({"ccomp", "xcomp", "csubj", "csubjpass"})
_CLAUSAL_RESTRICTIONS = frozenset(
    {
        "sentential",
        "that_comp",
        "sc_to_inf",
        "sc_ing",
        "oc_ing",
        "be_sc_ing",
        "wh_inf",
        "quotation",
        "ac_ing",
        "oc_to_inf",
        "wh_comp",
        "what_inf",
        "wheth_inf",
        "small_clause",
        "wh_extract",
        "wh_ing",
        "to_be",
        "tensed_that",
        "ac_to_inf",
        "for_comp",
        "np_to_inf",
        "oc_bare_inf",
    }
)


class ReferenceCatalogUnavailable(RuntimeError):
    """Pinned package assets are missing/corrupt; never a content refusal."""


class ReferenceCandidateLimit(ValueError):
    """The complete lexical candidate inventory exceeds its fixed bound."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    try:
        package = resources.files("app").joinpath("data")
        raw = package.joinpath("procedure_reference_lexicon_v1.json").read_bytes()
        license_bytes = package.joinpath("VERBNET_LICENSE.txt").read_bytes()
        if (
            len(raw) > 8 * 1024 * 1024
            or hashlib.sha256(raw).hexdigest() != PAYLOAD_SHA256
        ):
            raise ValueError("Lexical payload identity mismatch")
        if hashlib.sha256(license_bytes).hexdigest() != LICENSE_SHA256:
            raise ValueError("Lexical license identity mismatch")
        data = json.loads(raw)
        if (
            data["contract"] != "procedure-reference-lexicon-v1"
            or data["source"]["commit"] != SOURCE_COMMIT
            or data["source"]["license_sha256"] != LICENSE_SHA256
        ):
            raise ValueError("Lexical resource contract mismatch")
        return data
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ReferenceCatalogUnavailable(
            "Pinned procedure reference catalog unavailable"
        ) from exc


def catalog_metadata() -> dict[str, Any]:
    """Logical package identity only; caller receives no cached mutable object."""
    data = _catalog()
    return {
        "contract": data["contract"],
        "source_name": data["source"]["name"],
        "source_url": data["source"]["url"],
        "source_commit": SOURCE_COMMIT,
        "payload_sha256": PAYLOAD_SHA256,
        "license_file": "VERBNET_LICENSE.txt",
        "license_sha256": LICENSE_SHA256,
        "meaning": "possible_lexical_senses_not_source_facts_or_reference_absence",
    }


def _literal(graph: Any, start: int, end: int) -> dict[str, Any]:
    return {"start": start, "end": end, "text": graph.body[start:end]}


def _validate(graph: Any, predicate: int, identity: Any, clause: Any) -> None:
    if (
        type(identity) is not dict
        or not {"document_id", "document_version", "content_hash"} <= identity.keys()
        or type(identity["document_id"]) is not str
        or not identity["document_id"]
        or type(identity["document_version"]) is not int
        or identity["document_version"] < 1
        or identity["content_hash"] != hashlib.sha256(graph.body.encode()).hexdigest()
    ):
        raise ValueError("Actual immutable lexical source identity required")
    _canonical(identity)
    if type(clause) is not dict or set(clause) not in (
        {"start", "end"},
        {"start", "end", "text"},
    ):
        raise ValueError("Exact containing clause range required")
    first, last = clause["start"], clause["end"]
    if (
        type(first) is not int
        or type(last) is not int
        or not 0 <= first < last <= len(graph.body)
        or "text" in clause
        and clause["text"] != graph.body[first:last]
        or type(predicate) is not int
        or predicate not in graph.indices
    ):
        raise ValueError("Actual lexical predicate/clause binding mismatch")
    token = graph.tokens[predicate]
    if (
        token["pos"] not in {"VERB", "AUX"}
        or token["dep"] in {"amod", "aux", "auxpass"}
        or not (
            first <= graph.offset + token["start"] < graph.offset + token["end"] <= last
        )
    ):
        raise ValueError("Actual source content predicate required")
    if any(
        not first
        <= graph.offset + graph.tokens[i]["start"]
        < graph.offset + graph.tokens[i]["end"]
        <= last
        for i in graph.indices
    ):
        raise ValueError("Lexical graph extends beyond the containing clause")


def _lexical_units(graph: Any, predicate: int, data: Any) -> list[dict[str, Any]]:
    lemma = graph.lemma(predicate)
    names = sorted(
        name
        for name in data["lemma_index"]
        if name == lemma or name.startswith(lemma + "_")
    )
    attached = graph.children(predicate, {"prt", "prep"})
    units = []
    for name in names:
        parts = [] if name == lemma else name[len(lemma) + 1 :].split("_")
        chosen: list[int] = []
        unresolved_attachment = False
        for part in parts:
            matches = [
                i for i in attached if graph.lemma(i) == part and i not in chosen
            ]
            if len(matches) != 1:
                unresolved_attachment = len(matches) > 1 or any(
                    graph.lemma(i) == part
                    and graph.tokens[i]["dep"] in {"dep", "meta", "parataxis"}
                    for i in graph.children(predicate)
                )
                break
            chosen.append(matches[0])
        compatible = len(chosen) == len(parts)
        units.append(
            {
                "name": name,
                "token_indices": [predicate, *chosen],
                "tokens": [graph.span({i}) for i in [predicate, *chosen]],
                "decision": "matched"
                if compatible
                else "lexical_unknown"
                if unresolved_attachment
                else "lexical_incompatible",
                "lexical_prepositions": [
                    i for i in chosen if graph.tokens[i]["dep"] == "prep"
                ],
            }
        )
    return units


def _arguments(graph: Any, predicate: int, unit: Any) -> list[dict[str, Any]]:
    result = []
    for index in graph.children(predicate):
        dep = graph.tokens[index]["dep"]
        if dep in _SUBJECTS | _OBJECTS | _CLAUSES:
            kind = (
                "subject"
                if dep in _SUBJECTS
                else "clause"
                if dep in _CLAUSES
                else "object"
            )
            result.append(
                {
                    "token": index,
                    "kind": kind,
                    "attachment": dep,
                    "preposition": None,
                    "argument": graph.span(graph.subtree(index)),
                }
            )
        elif dep in {"prep", "agent"}:
            for obj in graph.children(index, {"pobj"}):
                result.append(
                    {
                        "token": obj,
                        "kind": "object"
                        if index in unit["lexical_prepositions"]
                        else "pp",
                        "attachment": dep,
                        "preposition": graph.lemma(index),
                        "preposition_token": index,
                        "argument": graph.span(graph.subtree(obj)),
                    }
                )
    return sorted(result, key=lambda row: row["argument"]["start"])


def _role_constraints(data: Any, member: Any) -> list[dict[str, Any]]:
    chain = []
    at = member["class"]
    seen = set()
    while at is not None:
        if at in seen or len(seen) >= 32:
            raise ReferenceCatalogUnavailable("Invalid lexical inheritance chain")
        seen.add(at)
        current = data["classes"][at]
        chain.append({"class": at, "role_declarations": current["role_declarations"]})
        at = current["parent"]
    return list(reversed(chain))


def _risk(  # noqa: C901 - complete bounded XML predicate/role inventory
    frame: Any, member: Any
) -> tuple[dict[int, list[Any]], list[Any]]:
    slots: dict[int, list[Any]] = {}
    implicit = []
    np_roles = {
        i: s["attributes"]["value"]
        for i, s in enumerate(frame["syntax"])
        if s["tag"] == "NP"
    }
    for index, role in np_roles.items():
        if role in {"Eventuality", "Subeventuality"}:
            slots.setdefault(index, []).append(
                {"kind": "eventuality_slot", "role": role}
            )
    for ordinal, pred in enumerate(frame["semantics"]):
        if pred["attributes"].get("value") not in _CONTENT_PREDICATES:
            continue
        args = [
            a
            for group in pred["children"]
            if group["tag"] == "ARGS"
            for a in group["children"]
        ]
        for arg in args:
            attributes = arg["attributes"]
            if (
                attributes.get("type") != "ThemRole"
                or attributes.get("value") in _ACTORS
            ):
                continue
            role = attributes["value"]
            reason = {
                "kind": "event_content_relation",
                "predicate_index": ordinal,
                "predicate": pred["attributes"],
                "role": role,
            }
            matches = [i for i, value in np_roles.items() if value == role]
            if role.startswith("?") or not matches:
                implicit.append(reason)
            else:
                for index in matches:
                    slots.setdefault(index, []).append(reason)
    mapping = member["attributes"].get("fn_mapping")
    if mapping in {"Execute_plan", "Compliance"}:
        targets = [i for i, role in np_roles.items() if role not in _ACTORS]
        reason = {
            "kind": "member_mapping_potential",
            "mapping": mapping,
            "meaning": "frame_risk_not_FE_to_argument_mapping",
            "candidate_slots": targets,
        }
        for index in targets:
            slots.setdefault(index, []).append(reason)
        if not targets:
            implicit.append(reason)
    return slots, implicit


def _restrictions(node: Any, actual: Any, graph: Any) -> tuple[bool, list[str]]:
    """Only a proved syntactic contradiction excludes; semantics stay unknown."""
    unknown = []
    for child in node["children"]:
        if child["tag"] == "SELRESTRS":
            if child["children"]:
                unknown.append("semantic_slot_restrictions_unassessed")
            continue
        if child["tag"] != "SYNRESTRS":
            unknown.append("unsupported_slot_constraint")
            continue
        # Nonempty trees with unsupported logic remain possible, never false.
        tests = []
        for restriction in child["children"]:
            attrs = restriction["attributes"]
            if (
                restriction["tag"] != "SYNRESTR"
                or attrs.get("type") not in _CLAUSAL_RESTRICTIONS
            ):
                tests.append(None)
                continue
            nominal = actual["kind"] != "clause" and graph.tokens[actual["token"]][
                "pos"
            ] in {"NOUN", "PROPN", "PRON"}
            tests.append(
                False
                if nominal and attrs.get("Value") == "+"
                else True
                if nominal and attrs.get("Value") == "-"
                else None
            )
        logic = child["attributes"].get("logic", "and")
        if (
            logic == "and"
            and False in tests
            or logic == "or"
            and tests
            and all(v is False for v in tests)
        ):
            return False, ["source_nominal_does_not_match_clausal_restriction"]
        if any(test is None for test in tests) or logic not in {"and", "or"}:
            unknown.append("syntactic_slot_restrictions_unassessed")
    return True, unknown


def _compatibility(  # noqa: C901 - one conservative complete frame-slot pass
    graph: Any, predicate: int, unit: Any, frame: Any, roles: Any
) -> tuple[str, list[Any], list[str]]:
    arguments = _arguments(graph, predicate, unit)
    syntax = frame["syntax"]
    verbs = [i for i, node in enumerate(syntax) if node["tag"] == "VERB"]
    unknown: list[str] = [
        "unsupported_frame_syntax:" + node["tag"]
        for node in syntax
        if node["tag"] not in {"NP", "VERB", "PREP"}
    ]
    bindings: list[Any] = []
    if len(verbs) != 1:
        return "unknown", bindings, ["unsupported_frame_predicate_inventory"]
    verb = verbs[0]
    if any(
        graph.tokens[i]["dep"] in {"auxpass", "nsubjpass", "csubjpass", "agent"}
        for i in graph.children(predicate)
    ):
        return "unknown", bindings, ["passive_role_alignment_unimplemented"]
    used = set()
    prep: Any = None
    for slot_index, slot in enumerate(syntax):
        tag = slot["tag"]
        if tag == "VERB":
            continue
        if tag == "PREP":
            prep = slot
            continue
        if tag != "NP":
            unknown.append("unsupported_frame_syntax:" + tag)
            continue
        role = slot["attributes"]["value"]
        kind = (
            "subject" if slot_index < verb else "pp" if prep is not None else "object"
        )
        matches = [
            a
            for a in arguments
            if a["token"] not in used
            and (a["kind"] == kind or kind == "object" and a["kind"] == "clause")
        ]
        if prep is not None:
            allowed = prep["attributes"].get("value")
            if allowed:
                matches = [a for a in matches if a["preposition"] in allowed.split()]
            elif prep["children"]:
                unknown.append("semantic_preposition_restrictions_unassessed")
        prep = None
        if (
            not matches
            and kind == "subject"
            and role in _ACTORS
            and not [a for a in arguments if a["kind"] == "subject"]
        ):
            bindings.append(
                {
                    "slot": slot_index,
                    "role": role,
                    "binding": "implicit_grammatical_actor",
                    "argument": None,
                }
            )
            continue
        if len(matches) != 1:
            if unknown or len(matches) > 1:
                return "unknown", bindings, [*unknown, "argument_alignment_unresolved"]
            return (
                "incompatible",
                bindings,
                ["required_source_argument_missing_or_ambiguous"],
            )
        actual = matches[0]
        possible, reasons = _restrictions(slot, actual, graph)
        if not possible:
            return "incompatible", bindings, reasons
        unknown.extend(reasons)
        used.add(actual["token"])
        bindings.append(
            {"slot": slot_index, "role": role, "binding": "source_argument", **actual}
        )
    if any(a["token"] not in used for a in arguments):
        unknown.append("extra_source_complement_or_adjunct_unresolved")
    if any(item["role_declarations"] for item in roles):
        unknown.append("inherited_semantic_role_restrictions_unassessed")
    if frame["other_fields"]:
        unknown.append("unsupported_additional_frame_fields")
    return "unknown" if unknown else "compatible", bindings, sorted(set(unknown))


def inspect_predicate(
    graph: Any, predicate_index: int, *, source_identity: Any, clause_range: Any
) -> dict[str, Any]:
    """Compile all possible lexical risk; callers own closure and admission."""
    _validate(graph, predicate_index, source_identity, clause_range)
    data = _catalog()
    units = _lexical_units(graph, predicate_index, data)
    analyses = []
    potential, unresolved = False, False
    count = 0
    for unit in units:
        if unit["decision"] == "lexical_incompatible":
            continue
        for member_id in data["lemma_index"][unit["name"]]:
            member = data["members"][member_id]
            cls = data["classes"][member["class"]]
            roles = _role_constraints(data, member)
            for frame_id in cls["applicable_frames"]:
                count += 1
                if count > MAX_FRAME_CANDIDATES:
                    raise ReferenceCandidateLimit(
                        "Complete lexical frame candidate budget exceeded"
                    )
                frame = data["frames"][frame_id]
                risk_slots, implicit = _risk(frame, member)
                if unit["decision"] == "lexical_unknown":
                    compatibility, bindings, reasons = (
                        "unknown",
                        [],
                        ["lexical_unit_attachment_unresolved"],
                    )
                else:
                    compatibility, bindings, reasons = _compatibility(
                        graph, predicate_index, unit, frame, roles
                    )
                risk_bindings = [
                    {**binding, "reasons": risk_slots[binding["slot"]]}
                    for binding in bindings
                    if binding["slot"] in risk_slots and binding["argument"] is not None
                ]
                possible = compatibility != "incompatible" and bool(
                    risk_slots or implicit
                )
                if possible:
                    potential |= bool(risk_bindings)
                    unresolved |= (
                        bool(implicit)
                        or compatibility == "unknown"
                        or len(risk_bindings) < len(risk_slots)
                    )
                analyses.append(
                    {
                        "lexical_unit": unit["name"],
                        "member": member,
                        "frame_id": frame_id,
                        "frame_origin_class": frame["origin_class"],
                        "compatibility": compatibility,
                        "compatibility_reasons": reasons,
                        "role_declaration_chain": roles,
                        "bindings": bindings,
                        "risk_slots": [
                            {"slot": i, "reasons": r}
                            for i, r in sorted(risk_slots.items())
                        ],
                        "implicit_risk": implicit,
                        "risk_bindings": risk_bindings if possible else [],
                        "possible_content_sense": possible,
                    }
                )
    matched = [unit for unit in units if unit["decision"] != "lexical_incompatible"]
    record = {
        "contract": CONTRACT,
        "catalog": catalog_metadata(),
        "source_identity": source_identity,
        "clause": _literal(graph, clause_range["start"], clause_range["end"]),
        "predicate_token": predicate_index,
        "predicate": graph.span({predicate_index}),
        "predicate_lemma": graph.lemma(predicate_index),
        "lexical_units": units,
        "lexical_status": "resource_checked" if matched else "not_in_resource",
        "analyses": analyses,
        "frame_candidate_count": count,
        "potential_instruction_content": bool(potential),
        "unresolved_risk": bool(unresolved),
        "interpretation": "risk_requires_source_reference_closure"
        if potential or unresolved
        else "ordinary_literal_arguments_under_declared_policy",
        "actual_sense": "NOT_ESTABLISHED",
        "entity_or_data_facts": "NOT_ASSERTED",
        "implicit_reference_absence": "NOT_ESTABLISHED",
        "reference_closure": "REQUIRED_SEPARATELY",
    }
    return deepcopy(record)
