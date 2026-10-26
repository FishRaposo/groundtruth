"""Preserve strongest already-accepted witnesses before compact presentation.

Raw QA margins rank witnesses for the same question part. They are neither
calibrated probabilities nor an additional factual-support judgment.
"""

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from app.services.answer_reader import ReaderSelection
from app.services.reader_attributes import ATTRIBUTE_CONTRACT


@dataclass(frozen=True)
class WitnessCover:
    indices: tuple[int, ...]
    diagnostics: dict[str, Any]


def select_witness_cover(
    selections: list[ReaderSelection], *, limit: int = 3
) -> WitnessCover:
    count = selections[0].diagnostics.get("part_count") if selections else None
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 8:
        raise ValueError("Reader witness cover requires one to eight question parts.")
    accepted = [index for index, value in enumerate(selections) if value.span]
    witnesses: dict[int, set[int]] = {}
    records = []
    for part in range(count):
        candidates = [
            index
            for index in accepted
            if part in selections[index].diagnostics.get("covered_parts", [])
        ]
        margins = {}
        structures = {}
        attributes = {}
        for index in candidates:
            diagnostic = next(
                (
                    item
                    for item in selections[index].diagnostics.get("parts", [])
                    if item.get("index") == part
                ),
                {},
            )
            score = diagnostic.get("null_margin")
            feature = diagnostic.get("procedure_evidence")
            structures[index] = feature if isinstance(feature, dict) else {}
            attribute = diagnostic.get("attribute_evidence")
            attributes[index] = attribute if isinstance(attribute, dict) else {}
            if (
                isinstance(score, (int, float))
                and not isinstance(score, bool)
                and math.isfinite(score)
            ):
                margins[index] = float(score)
        # Historical/custom selections without margins keep their existing
        # coverage behavior. An absent score must never become a fabricated one.
        scored = bool(candidates) and len(margins) == len(candidates)
        procedure = scored and all(
            structures[index].get("requested") is True for index in candidates
        )
        structured = {
            index
            for index in candidates
            if procedure and structures[index].get("selected_sequence") is True
        }
        ranked = structured or set(candidates)
        attribute_ready = scored and all(
            attributes[index].get("contract") == ATTRIBUTE_CONTRACT
            and attributes[index].get("requested") is True
            for index in candidates
        )
        matching_attribute = {
            index
            for index in ranked
            if attribute_ready
            and attributes[index].get("selected_clause_matches") is True
        }
        ranked = matching_attribute or ranked
        best = min(margins[index] for index in ranked) if scored else None
        witnesses[part] = {
            index for index in ranked if not scored or margins[index] == best
        }
        records.append(
            {
                "part": part,
                "candidate_indices": sorted(witnesses[part]),
                "null_margin": best,
                "score_status": "recorded" if scored else "unknown",
                "structure_preference": "selected-topic-sequence-among-accepted"
                if structured
                else "not_applicable_or_unknown",
                "attribute_preference": "requested-terms-in-selected-clause"
                if matching_attribute
                else "not_applicable_or_unknown",
            }
        )
    cover = next(
        (
            group
            for size in range(1, min(limit, len(accepted)) + 1)
            for group in combinations(accepted, size)
            if all(set(group) & candidates for candidates in witnesses.values())
        ),
        (),
    )
    return WitnessCover(
        cover,
        {
            "method": "strongest-accepted-part-witness-v5",
            "ranking_semantics": (
                "selected topic-bound sequence or explicit attribute terms in the "
                "selected clause among accepted witnesses, then lowest raw "
                "null-margin; uncalibrated and not entailment"
            ),
            "missing_scores": "legacy coverage; no invented ranking",
            "tie_break": "fewest citations then original candidate order",
            "citation_limit": limit,
            "selected_candidate_indices": list(cover),
            "witnesses": records,
            "decision": "covered" if cover else "no_cover_within_citation_limit",
        },
    )
