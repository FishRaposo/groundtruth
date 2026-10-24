# Exposed development observations after the failed blind comparison

**Acceptance remains OPEN.** These observations use already exposed cases.
The [first blind-v4 comparison](../answer-coverage-v4/README.md) remains failed
and immutable. Its later development results cannot replace it.

## V10, fixed local RoBERTa threshold4

| Set | Correct answers | Correct negatives | Limits |
| --- | --- | --- | --- |
| Earlier development80 |46/48|32/32|One false refusal and one wrong procedure answer |
| Exposed v4 cases200 |95/120|80/80|18 false refusals and seven wrong/incomplete answers |

Both use actual authenticated HTTP, new SQLite backups, inline ingestion data,
cached semantic embeddings and CPU extraction. The source stayed unchanged
during measurement, and original database bytes stayed unchanged. All280 rows
pass the portable integrity re-score; execution, authorization, citation and
span-integrity failures are zero. These are synthetic, agent-authored labels.
Neither human validity nor general answer quality is established.

The [preservation audit](preservation-audit.json) verifies all435 archive payloads,
both280-row observations,16 original evidence files and21 sealed V4 files. It
finds zero matches for the actual private seed keys; private manifests are absent.

The [observation record](v10-observation.json) binds the
[exact report/source archive](v10-exposed-development-observation.zip), including
156 measured source/test/tool files verified against their recorded raw hashes.
Later working files are different. No current-source result is inferred from
that archive. Its checksums and preservation code are included.

## Independent review and subsequent development

The [review archive](v10-independent-review.zip) retains three material findings:
embedded directive verbs corrupting interrogatives, a one-letter named subject
inheriting another scope, and a modal sequence request losing procedural intent.
The parent reproduced four failing assertions with30 passing controls before
repair;68 affected checks then passed. Independent recheck passes all16 retained
assertions with five source/test hashes unchanged. The197-reader and initial
type logs predate these last repairs and are retained at their exact scopes.

## V11, same fixed threshold, later source

The [V11 record](v11-observation.json) and
[exact observation/source archive](v11-exposed-development-observation.zip)
bind157 measured files. The same real-HTTP development workflow reaches
**112/120 answers and80/80 negatives**, with four false refusals and four
wrong/incomplete positive answers. The earlier development80 returns to
**47/48 answers and32/32 negatives**. Source and original databases stayed
unchanged; all280 rows re-score with zero execution/access/citation/span errors.
This remains below114/120 and is exposed development, not acceptance.

The [V11 review archive](v11-independent-review.zip) retains three additional
defects: session-start location confused with time, plural own-exception
references rejected, and a generic heading borrowing a different named subject.
Five owned RED cases precede41 affected passing checks. Independent recheck
resolves the three material findings and verifies ordinary accepted-span/margin
fallback when the formatting prior is withheld; it also retains all16 V10
controls. The original14-probe report still has two nonpassing expectations:
deliberate removal of the prior when another name is present, and the documented
original-layout limitation. Neither is relabeled as a passing invariant.

Ingestion collapses whitespace. The formatting prior can inspect only paragraph
breaks that remain in canonical context; it cannot guarantee original-layout
isolation or establish factual coreference. Source formatting is optional and
does not turn a null model prediction into an answer. Review fixes and later
role-question preparation are different source from the measured V11 version.

No fresh blind set has been authored for these repairs; the owner review
instance remains unpromoted. Packaging, production browser and final full-suite
gates for the latest source remain pending.

Return to the [development entrypoint](../../answer-coverage-development-v3.md)
or the [previous measured checkpoint](../answer-coverage-v5/README.md).
