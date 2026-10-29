"""UNITONLY natural-prose fixtures; no observed parser/NLI behavior.

Each test names a structural defect this component can actually prevent. Source
proposal DTOs are handcrafted independent inputs, not actual model observations.
"""

import unittest
from copy import deepcopy
from dataclasses import replace

from app.services import required_reference_closure as c


def fixture(doc, label, body=None, *, refs=(), kind="procedure", title=None):
    body = (
        body
        if body is not None
        else f"The {kind} is named {label}. Perform the checks."
    )
    source = c.make_snapshot(doc, title or label, body)
    whole = c.RawRange(0, len(body), body)
    at = body.index(label)
    declaration = c.Declaration(
        source.identity, kind, label, whole, c.RawRange(at, at + len(label), label)
    )
    references = []
    search_at = 0
    for literal in refs:
        at = body.index(literal, search_at)
        search_at = at + len(literal)
        references.append(
            c.RequiredReference(
                source.identity,
                literal,
                whole,
                c.RawRange(at, at + len(literal), literal),
            )
        )
    analysis = c.SourceAnalysis(
        source.identity,
        "UNITONLY:779-external-target-proposals",
        '{"fixture":"UNITONLY","origin":"external_instruction_target"}',
        (whole,),
        (declaration,),
        tuple(references),
    )
    return source, analysis


def binding(analysis, target_source, target_analysis, index=0):
    reference = analysis.references[index]
    declaration = next(
        d for d in target_analysis.declarations if d.label == reference.target_literal
    )
    return c.BindingEvidence(
        reference,
        target_source.identity,
        declaration,
        reference.raw,
        '{"fixture":"UNITONLY","relation":"source_required_target"}',
    )


def two():
    a, aa = fixture(
        "manual",
        "Valve inspection",
        "Valve inspection is the complete procedure. "
        "If the seal fails, consult Seal recovery.",
        refs=("Seal recovery",),
    )
    b, ba = fixture(
        "annex",
        "Seal recovery",
        "Seal recovery is the required appendix. Stop the pump. Log the defect.",
        kind="appendix",
    )
    return (a, b), (aa, ba), (binding(aa, b, ba),)


def chain(count):
    snapshots, analyses = [], []
    for i in range(count):
        body = f"Plan {i} is the complete procedure. Check the valve."
        refs = ()
        if i + 1 < count:
            body += f" Required further instructions are in Plan {i + 1}."
            refs = (f"Plan {i + 1}",)
        source, analysis = fixture(f"doc{i}", f"Plan {i}", body, refs=refs)
        snapshots.append(source)
        analyses.append(analysis)
    bindings = tuple(
        binding(analyses[i], snapshots[i + 1], analyses[i + 1])
        for i in range(count - 1)
    )
    return tuple(snapshots), tuple(analyses), bindings


class ClosureTests(unittest.TestCase):
    def build(self, inputs, root="manual", **kwargs):
        snapshots, analyses, bindings = inputs
        return c.reconstruct_closure(
            root,
            snapshots=snapshots,
            analyses=analyses,
            binding_evidence=bindings,
            **kwargs,
        )

    def valid(self, record, inputs, root="manual", **kwargs):
        snapshots, analyses, bindings = inputs
        return c.validate_closure(
            record,
            root_document_id=root,
            snapshots=snapshots,
            analyses=analyses,
            binding_evidence=bindings,
            **kwargs,
        )

    def refused(self, code, inputs, root="manual", **kwargs):
        with self.assertRaises(c.ClosureRefusal) as caught:
            self.build(inputs, root, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_complete_single_body_is_retained_without_publication_permission(self):
        # Defect: selected-span copying drops the trailing governing condition.
        body = (
            "Valve inspection is the complete procedure. "
            "Check the seal. If damaged, stop.\n"
        )
        source, analysis = fixture("manual", "Valve inspection", body)
        record = self.build(((source,), (analysis,), ()))
        self.assertEqual(record["status"], "PENDING_INDEPENDENT_GATES")
        self.assertEqual(record["rendered_text"], body)
        self.assertEqual(record["structural_status"], "CLOSED")
        self.assertEqual(record["support_or_permissions"], "NOT_ASSESSED")
        self.assertIn(
            "actual_source_faithful_nli_and_answer_support", record["remaining_gates"]
        )

    def test_required_appendix_included_whole_and_cited_at_exact_offsets(self):
        # Defect: reference target is found without actually including its content.
        inputs = two()
        record = self.build(inputs)
        self.assertEqual(record["ordered_document_ids"], ["manual", "annex"])
        self.assertEqual(
            record["rendered_text"], inputs[0][0].body + "\n\n" + inputs[0][1].body
        )
        self.assertEqual(
            record["inclusions"][1]["source_range"],
            {"start": 0, "end": len(inputs[0][1].body), "text": inputs[0][1].body},
        )
        self.assertEqual(
            record["inclusions"][1]["citation_source"]["document_id"], "annex"
        )
        self.assertTrue(self.valid(record, inputs))

    def test_recursive_required_content_is_not_truncated_at_first_reference(self):
        inputs = chain(3)
        record = self.build(inputs, "doc0")
        self.assertEqual(record["ordered_document_ids"], ["doc0", "doc1", "doc2"])
        self.assertEqual(len(record["edges"]), 2)
        self.assertTrue(record["rendered_text"].endswith(inputs[0][2].body))

    def test_shared_dependency_dag_keeps_all_edges_and_one_full_body(self):
        a, aa = fixture(
            "manual",
            "Root",
            "Root governs the procedure. Read North and South.",
            refs=("North", "South"),
        )
        b, ba = fixture(
            "north",
            "North",
            "North defines the process. Read Common.",
            refs=("Common",),
        )
        d, da = fixture("common", "Common")
        e, ea = fixture(
            "south",
            "South",
            "South defines the process. Read Common.",
            refs=("Common",),
        )
        inputs = (
            (a, b, d, e),
            (aa, ba, da, ea),
            (
                binding(aa, b, ba, 0),
                binding(aa, e, ea, 1),
                binding(ba, d, da),
                binding(ea, d, da),
            ),
        )
        record = self.build(inputs)
        self.assertEqual(
            record["ordered_document_ids"], ["manual", "north", "common", "south"]
        )
        self.assertEqual(len(record["edges"]), 4)
        self.assertEqual(len(record["inclusions"]), 4)

    def test_exact_declaration_label_can_resolve_differently_titled_document(self):
        sources, analyses, bindings = two()
        sources = (sources[0], replace(sources[1], title="Operations supplement"))
        record = self.build((sources, analyses, bindings))
        self.assertEqual(
            [p["basis"] for p in record["edges"][0]["proposals"]], ["EXACT_DECLARATION"]
        )

    def test_unique_title_and_declaration_without_binding_stays_unresolved(self):
        # Defect: producer turns unique title lookup directly into closure.
        sources, analyses, _ = two()
        self.refused("MISSING_INDEPENDENT_BINDING_EVIDENCE", (sources, analyses, ()))

    def test_title_proposal_alone_cannot_claim_declared_target(self):
        sources, analyses, bindings = two()
        other, oa = fixture("annex", "Other procedure", title="Seal recovery")
        bad = replace(
            bindings[0], target=other.identity, target_declaration=oa.declarations[0]
        )
        self.refused(
            "BINDING_TARGET_DECLARATION_DIFFERS",
            ((sources[0], other), (analyses[0], oa), (bad,)),
        )

    def test_missing_required_target_refuses(self):
        sources, analyses, _ = two()
        self.refused("MISSING_REQUIRED_TARGET", ((sources[0],), (analyses[0],), ()))

    def test_ambiguous_same_title_refuses_despite_one_binding(self):
        sources, analyses, bindings = two()
        x, xa = fixture("rival", "Rival", title="Seal recovery")
        self.refused(
            "AMBIGUOUS_REQUIRED_TARGET", (sources + (x,), analyses + (xa,), bindings)
        )

    def test_ambiguous_declaration_alias_refuses(self):
        sources, analyses, bindings = two()
        x, xa = fixture("rival", "Seal recovery", title="Independent supplement")
        self.refused(
            "AMBIGUOUS_REQUIRED_TARGET", (sources + (x,), analyses + (xa,), bindings)
        )

    def test_self_reference_cycle_refuses(self):
        a, aa = fixture(
            "manual", "Root", "Root is the process. Read Root.", refs=("Root",)
        )
        self.refused("REQUIRED_REFERENCE_CYCLE", ((a,), (aa,), (binding(aa, a, aa),)))

    def test_two_document_cycle_refuses(self):
        a, aa = fixture(
            "manual", "Root", "Root is the process. Read Annex.", refs=("Annex",)
        )
        b, ba = fixture(
            "annex", "Annex", "Annex is the process. Read Root.", refs=("Root",)
        )
        self.refused(
            "REQUIRED_REFERENCE_CYCLE",
            ((a, b), (aa, ba), (binding(aa, b, ba), binding(ba, a, aa))),
        )

    def test_eight_documents_allowed_ninth_refuses_without_partial_record(self):
        self.assertEqual(len(self.build(chain(8), "doc0")["inclusions"]), 8)
        self.refused("REQUIRED_DOCUMENT_BUDGET", chain(9), "doc0")

    def test_bound_cannot_be_raised_or_boolean(self):
        for value in (9, True, 0, 8.0):
            with self.subTest(bound=value):
                self.refused("INVALID_DOCUMENT_BOUND", two(), max_documents=value)

    def test_binding_source_context_cannot_delete_a_condition(self):
        sources, analyses, bindings = two()
        literal = bindings[0].reference.literal_range
        bad = replace(bindings[0], source_relation=literal)
        self.refused("BINDING_RELATION_CONTEXT", (sources, analyses, (bad,)))

    def test_duplicate_binding_is_ambiguous_even_when_identical(self):
        sources, analyses, bindings = two()
        self.refused("AMBIGUOUS_BINDING_EVIDENCE", (sources, analyses, bindings * 2))

    def test_known_unresolved_reference_analysis_refuses(self):
        sources, analyses, bindings = two()
        changed = (
            analyses[0],
            replace(analyses[1], unresolved=("unbound_required_reference",)),
        )
        self.refused("UNRESOLVED_REFERENCE_ANALYSIS", (sources, changed, bindings))

    def test_original_body_hash_mismatch_refuses(self):
        sources, analyses, bindings = two()
        changed = (replace(sources[0], body=sources[0].body + " Changed."), sources[1])
        self.refused("CHANGED_SNAPSHOT", (changed, analyses, bindings))

    def test_authoritative_coherent_changed_snapshot_invalidates_old_record(self):
        inputs = two()
        record = self.build(inputs)
        source, analysis = fixture(
            "manual", "Valve inspection", "Valve inspection now forbids the operation."
        )
        self.assertFalse(self.valid(record, ((source,), (analysis,), ())))

    def test_unselected_source_is_inventory_bound(self):
        sources, analyses, bindings = two()
        x, xa = fixture("unused", "Other operations")
        original = (sources + (x,), analyses + (xa,), bindings)
        record = self.build(original)
        self.assertEqual(len(record["source_inventory"]), 3)
        changed = (
            sources + (replace(x, metadata_json='{"changed":true}'),),
            analyses + (xa,),
            bindings,
        )
        self.assertFalse(self.valid(record, changed))

    def test_reconstruction_rejects_omitted_edge_inclusion_source_and_condition(self):
        # Defect: coherent producer record omits a required body or governor.
        inputs = two()
        record = self.build(inputs)
        mutations = []
        for field in (
            "edges",
            "inclusions",
            "source_inventory",
            "independent_source_analyses",
        ):
            changed = deepcopy(record)
            changed[field].pop()
            mutations.append(changed)
        changed = deepcopy(record)
        changed["rendered_text"] = changed["rendered_text"].replace(
            "If the seal fails, ", ""
        )
        mutations.append(changed)
        changed = deepcopy(record)
        changed["remaining_gates"] = []
        mutations.append(changed)
        changed = deepcopy(record)
        changed["independent_binding_evidence"][0]["origin_json"] = "{}"
        mutations.append(changed)
        for index, mutated in enumerate(mutations):
            with self.subTest(mutation=index):
                self.assertFalse(self.valid(mutated, inputs))

    def test_bool_int_and_range_identity_tampering_rejects(self):
        inputs = two()
        original = self.build(inputs)
        for field, value in (("ordinal", False), ("ordinal", 1)):
            changed = deepcopy(original)
            changed["inclusions"][0][field] = value
            self.assertFalse(self.valid(changed, inputs))
        changed = deepcopy(original)
        changed["inclusions"][1]["output_range"]["start"] += 1
        self.assertFalse(self.valid(changed, inputs))
        changed = deepcopy(original)
        changed["edges"][0]["target"]["document_version"] = True
        self.assertFalse(self.valid(changed, inputs))

    def test_unicode_crlf_offsets_use_original_codepoints(self):
        a, aa = fixture(
            "manual",
            "Inspeção 🧭",
            "Inspeção 🧭: verifique.\r\nConsulte Apêndice ç.\r\n",
            refs=("Apêndice ç",),
        )
        b, ba = fixture(
            "annex",
            "Apêndice ç",
            "Apêndice ç: pare.\r\nRegistre a condição.\r\n",
            kind="appendix",
        )
        inputs = ((a, b), (aa, ba), (binding(aa, b, ba),))
        record = self.build(inputs)
        interval = record["inclusions"][1]["output_range"]
        self.assertEqual(
            record["rendered_text"][interval["start"] : interval["end"]], b.body
        )
        self.assertEqual(record["edges"][0]["reference"]["literal_range"]["start"], 33)
        self.assertTrue(self.valid(record, inputs))

    def test_chunk_coverage_gap_refuses(self):
        sources, analyses, bindings = two()
        body = sources[0].body
        chunk = c.SourceChunk("partial", 0, c.RawRange(1, len(body), body[1:]))
        changed = (replace(sources[0], chunks=(chunk,)), sources[1])
        self.refused("CHUNK_COVERAGE_GAP", (changed, analyses, bindings))

    def test_multiple_chunks_preserve_original_membership(self):
        source, analysis = fixture("manual", "Root")
        body = source.body
        chunks = (
            c.SourceChunk("first", 0, c.RawRange(0, 5, body[:5])),
            c.SourceChunk("second", 1, c.RawRange(5, len(body), body[5:])),
        )
        inputs = ((replace(source, chunks=chunks),), (analysis,), ())
        record = self.build(inputs)
        self.assertEqual(
            [x["chunk_id"] for x in record["source_inventory"][0]["chunks"]],
            ["first", "second"],
        )

    def test_missing_authorized_publication_and_cross_workspace_refuse(self):
        sources, analyses, bindings = two()
        universe = c.AuthorizedUniverse("{}", tuple(s.identity for s in sources))
        self.refused(
            "MISSING_OR_CHANGED_AUTHORIZED_SNAPSHOT",
            ((sources[0],), (analyses[0],), ()),
            universe=universe,
        )
        altered = replace(
            sources[1], identity=replace(sources[1].identity, workspace_id="other")
        )
        self.refused(
            "CROSS_WORKSPACE_NOT_SUPPORTED", ((sources[0], altered), analyses, bindings)
        )

    def test_source_unit_and_reference_range_forgery_refuses(self):
        sources, analyses, bindings = two()
        raw = analyses[0].source_units[0]
        bad = replace(
            analyses[0], source_units=(replace(raw, start=1, text=raw.text[1:]),)
        )
        self.refused("SOURCE_UNIT_COVERAGE", (sources, (bad, analyses[1]), bindings))
        bad_ref = replace(analyses[0].references[0], target_literal="Different")
        bad = replace(analyses[0], references=(bad_ref,))
        self.refused("REFERENCE_LITERAL_RANGE", (sources, (bad, analyses[1]), ()))

    def test_producer_success_flag_and_callback_are_not_admissible_inputs(self):
        sources, analyses, _ = two()
        with self.assertRaises(TypeError):
            c.reconstruct_closure(
                "manual", snapshots=sources, analyses=analyses, validated=True
            )
        with self.assertRaises(TypeError):
            c.reconstruct_closure(
                "manual", snapshots=sources, analyses=analyses, evaluator=lambda: True
            )
        self.assertFalse(
            c.validate_closure(
                True, root_document_id="manual", snapshots=sources, analyses=analyses
            )
        )

    def test_unknown_contract_and_extra_fields_cannot_downgrade_record(self):
        inputs = two()
        record = self.build(inputs)
        record["contract"] = "complete-immutable-procedure-v5"
        self.assertFalse(self.valid(record, inputs))
        record = self.build(inputs)
        record["all_resolved"] = True
        self.assertFalse(self.valid(record, inputs))

    def test_duplicate_json_metadata_and_boolean_version_refuse(self):
        sources, analyses, bindings = two()
        altered = replace(sources[0], metadata_json='{"a":1,"a":1}')
        self.refused(
            "NON_CANONICAL_METADATA", ((altered, sources[1]), analyses, bindings)
        )
        altered = replace(
            sources[0], identity=replace(sources[0].identity, document_version=True)
        )
        self.refused("INVALID_VERSION", ((altered, sources[1]), analyses, bindings))

    def test_boolean_identity_inside_independent_analysis_refuses(self):
        # Defect: dataclass equality accepts True as immutable version1.
        sources, analyses, bindings = two()
        false_identity = replace(sources[0].identity, document_version=True)
        altered = replace(analyses[0], source=false_identity)
        self.refused("INVALID_VERSION", (sources, (altered, analyses[1]), bindings))

    def test_reference_order_must_follow_original_source_offsets(self):
        # Defect: adapter order changes output/reference order without source basis.
        a, aa = fixture(
            "manual", "Root", "Root requires North then South.", refs=("North", "South")
        )
        b, ba = fixture("north", "North")
        d, da = fixture("south", "South")
        altered = replace(aa, references=tuple(reversed(aa.references)))
        self.refused(
            "REFERENCE_SOURCE_ORDER",
            (
                (a, b, d),
                (altered, ba, da),
                (binding(aa, b, ba, 0), binding(aa, d, da, 1)),
            ),
        )

    def test_body_universe_and_reference_budgets_refuse(self):
        # Defect: bounded documents leave unbounded bytes or reference inputs.
        huge, ha = fixture("manual", "Root", "Root " + "x" * (128 * 1024))
        self.refused("BODY_BUDGET", ((huge,), (ha,), ()))
        source, analysis = fixture("manual", "Root")
        self.refused("UNIVERSE_BUDGET", ((source,) * 129, (analysis,) * 129, ()))
        source, analysis = fixture(
            "manual", "Root", "Root." + " Consult Annex." * 129, refs=("Annex",) * 129
        )
        self.refused("REFERENCE_BUDGET", ((source,), (analysis,), ()))

    def test_retained_origin_and_declaration_budgets_refuse(self):
        sources, analyses, bindings = two()
        altered = replace(
            analyses[0], origin_json='{"trace":"' + "x" * (128 * 1024) + '"}'
        )
        self.refused("JSON_BUDGET", (sources, (altered, analyses[1]), bindings))
        altered = replace(analyses[0], declarations=analyses[0].declarations * 513)
        self.refused("DECLARATION_BUDGET", (sources, (altered, analyses[1]), bindings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
