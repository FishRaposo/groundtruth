# Third-party notices

## Internally vendored operator core subset

GroundTruth contains a narrow, internally namespaced copy of the modules it
uses from `FishRaposo/operator-shared-core` v1.3.0. The source is pinned to
commit `dbf276a7708da65b55e1f10b35af634b300d1f07` and lives under
`apps/api/app/internal/vendor_core/`.

The vendored closure is limited to configuration, database helpers, document
parsing, deterministic embeddings and judges, errors, logging, LLM metrics and
pricing, Celery setup, and the HTTP client required by the embedding gateway.
Its imports are rewritten to the GroundTruth-owned namespace. The rest of
GroundTruth neither installs nor imports an external `shared_core` package.

Those modules remain under their original MIT license. The complete upstream
license text ships beside the vendored source at
[`apps/api/app/internal/vendor_core/LICENSE`](apps/api/app/internal/vendor_core/LICENSE),
including the `Copyright (c) 2026 Operator Systems` notice, grant, conditions,
and warranty disclaimer. GroundTruth itself is distributed under the MIT license
in [`LICENSE`](LICENSE).

## Optional local embedding model

The explicit model setup downloads `sentence-transformers/all-MiniLM-L6-v2`,
revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, separately from this source
distribution. Its model card declares Apache-2.0. The weights are not bundled in
GroundTruth wheels or the recruiter preview. Preserve upstream notices if you
redistribute model assets. See the [pinned model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md)
and [Apache-2.0 license](https://www.apache.org/licenses/LICENSE-2.0).

## Optional local extractive reader

The answer-coverage profile separately downloads Deepset's
`deepset/minilm-uncased-squad2`, revision
`934656cdda79824eabf503ed56e15c01ddbdbe3f`, based on Microsoft's MiniLM and
fine-tuned for extractive question answering on SQuAD 2.0. Its pinned model card
declares CC-BY-4.0. Attribute the model to Deepset and preserve its upstream
notices when redistributing assets. GroundTruth does not bundle its weights in
wheels or the offline preview, train the model, or claim the upstream benchmark
as its own application evaluation.

See the [pinned model card](https://huggingface.co/deepset/minilm-uncased-squad2/blob/934656cdda79824eabf503ed56e15c01ddbdbe3f/README.md)
and [Creative Commons Attribution 4.0 license](https://creativecommons.org/licenses/by/4.0/).
