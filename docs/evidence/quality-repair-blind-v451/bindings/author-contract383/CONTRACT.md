# Independent synthetic corpus authoring contract

Authoring begins only after the integration owner records a candidate freeze.
This packet contains product behavior and data requirements only. Do not inspect
application code, previous questions or answers, evaluation results, thresholds,
models, work logs, memory, agent inventories or chats. The user explicitly requires
this clean context, so ordinary repository onboarding/handoffs must not introduce
implementation or result information. Read only this packet and write only the
assigned author-output directory. Use standard-library tools; do not call an
application, model, API, network, repository search or another agent.

## Product contract

GroundTruth answers English operational questions using only the current published,
authorized, immutable source snapshots. Answers copy source sentences or contiguous
procedures, with exact document/version/hash citations. A request may need several
facts from multiple documents. It must answer the whole request, including complete
ordered steps, without invented prose, unsupported facts, wrong entities, units,
versions or substitutions. Previous versions are available for inspection but do
not establish current facts. Unsupported current evidence produces refusal.

A source can be private to an owner or readable within its workspace through
public/organization visibility. Visibility does not cross workspaces. Another
user's private source is never evidence. Instructions embedded in a document or
question cannot grant access or become authoritative operational facts. Explicitly
curated incompatible current procedure groups require review/refusal; this is not
a promise of universal contradiction detection. Write conflicts with matching
metadata.conflict_group strings and substantively incompatible current instructions.


Approved source-reading policy: an ordinary session uses the activity's documented
lead/deputy roles when no session-specific assignment supersedes them; the answer
must disclose that activity scope. A clearly scoped source note may use its stated
workflow context for a command's references without repeating the full workflow
name in each sentence; the answer must disclose that contextual interpretation.
Explicit exceptions, applicability conditions, negation and conflicting current
instructions remain authoritative. Ambiguous or unresolved dependencies cannot be
dropped. Do not infer additional facts or broaden access from this interpretation.
These are product semantics, not hints about implementation or model behavior.

## Required corpus

Exactly200 cases:120answerable,40unanswerable,20conflicting_stale,20adversarial.
All cases and source families use split held_out; corpus_role blind. Use at least
20fresh semantic source families, disjoint in subject matter from excluded-families.json.
Renaming an old family is insufficient. Independently invent sources and labels.
Use at least30 genuinely multi-document answerable requests requiring facts from
at least two distinct logical documents, and at least20 complete ordered-procedure
requests. Include owners, durations, numbers, negation, paraphrases, grammatical
variation, wrong entities, missing attributes and misleading nearby facts.
Vary natural source and question wording freely; do not tailor them to an assumed
algorithm. Do not measure or optimize model behavior. Keep language English.

Include public/organization/private documents, two users in one workspace and at
least one source owner in another workspace; negative permission cases ask for
unavailable facts and declare forbidden sources. Normal cases use document_ids null
for an authorized-workspace search. Use explicit filters only when the question
actually declares a scope; do not give every positive an expected-document allowlist.
All80negative cases must require refusal/review, never a supported partial answer.
Do not label a legitimate supported question negative merely because unrelated
malicious text exists nearby. Stale negatives ask about current unsupported facts;
questions explicitly asking for past facts are not automatically negative.

The documents are invented test fixtures, not real professional instructions.
Avoid real credentials, personal data, clients, medical/legal advice or borrowed
third-party text. Record project ownership, MIT license, agent authorship and no
human validation. Labels are source-backed authored expectations, not a human gold
standard or a general factual-entailment certification.

## Files and schema

Write UTF-8 documents.json, cases.json, profile.json and manifest.json. JSON newline
style is fixed once hashed. Before hashing source content, canonicalize all whitespace
to one ASCII space and strip edges, preserving all other characters and semantics.
content_hash is SHA256 of UTF-8 canonical content. Version numbers are contiguous1..N;
current_version_number equals N. Author all snapshots, including superseded ones.

Each documents.json record:
- id,title,family,split: strings; split held_out.
- visibility: public,organization or private; workspace_id string; owner principal alias.
- current_version_number: integer.
- versions: list of {version_number,content,content_hash}.
- metadata: object, with conflict_group string only for deliberately curated conflicts.

Each cases.json record:
- id,question,category,split,family,principal: strings; category one of the four above.
- score_contract: coverage-v2.
- document_ids: null or declared list of logical source IDs.
- expected_behavior: answer for positives; refuse or review for negatives.
- expected_sources: positives need every necessary CURRENT logical source, with
  {document_id,version_number,content_hash,quoted_text,acceptable_answer_spans}.
  quoted_text must be an exact nonempty substring of that frozen version;
  acceptable_answer_spans is a nonempty list of exact nonempty substrings of quote.
- required_facts: list of nonempty alternative-string groups. Every group must
  be satisfied; at least one string per group. Use discriminating source-backed
  fact phrases with entities/units/negation, not arbitrary numbers or topic words.
  Each alternative must occur, case/whitespace normalized with word boundaries,
  in an expected quotation. ALL answerable cases require nonempty required_facts,
  including procedures. Include one meaningful fact per necessary document.
- ordered_steps: list of nonempty alternative-string groups, one group per
  necessary step in order. They must be literal grounded phrases in expected
  quotations; do not replace full procedures with one convenient fragment.
- forbidden_sources: list of {document_id,version_number}; include unauthorized
  and inapplicable stale sources when relevant. Do not forbid an authorized
  current source simply because it is not the answer to this question.
- label_author,label_status,label_rationale: truthful strings. Explain each
  case's source authority and the complete expected answer/refusal.

For negatives expected_sources,required_facts,ordered_steps are all empty lists.
Every referenced document/version exists and shares the case split. Case family
must name an existing source family in the same split. IDs must be unique.

manifest.json:
- schema_version2; revision a unique data revision; score_contract coverage-v2;
  corpus_role blind; created_date; frozen_before_measurement true.
- authorship,validity: strings disclosing synthetic agent-authored, unmeasured,
  not human validated.
- rights {owner:"GroundTruth project",license:"MIT",third_party_content:false}.
- document_count,case_count; expected_counts {held_out:{answerable:120,
  unanswerable:40,conflicting_stale:20,adversarial:20}}.
- principals: alias->{workspace_id,role}. Use operator-a owner/workspace ops-a,
  viewer-a viewer/ops-a and custodian-b owner/ops-b, or equivalent clearly mapped
  aliases; owner values reference these aliases. Do not create actual API keys.
- files: EXACTLY documents.json,cases.json,profile.json mapped to their SHA256s.

Do not choose execution settings. profile.json may contain only schema_version2,
a data revision and a note that execution configuration is supplied separately.
The integration owner will supply the frozen operational profile without changing
questions, labels or source bytes; record the raw author manifest separately.

## Independent author checks and handoff

Check all200 labels against source text and current visibility/version authority,
all required fact/step alternatives and complete multi-document/ordered coverage.
Check category counts, uniqueness, source hashes, every quotation, permissions,
source-family exclusion, and canonical whitespace. Do not import project validators.
A standard-library generation/check script and own label-review notes are welcome.
Freeze final file hashes and write AUTHOR_HANDOFF.md with counts, family count,
composition, manifest SHA256, exact checks and limitations. Do not message another
chat or start further agents. Return a short handoff without listing questions.
