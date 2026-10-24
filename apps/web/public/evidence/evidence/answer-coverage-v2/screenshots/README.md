# Reader candidate screenshots

Observed 2026-10-24 against the frozen reader candidate and production frontend.
These captures supplement the [browser record](../browser-observations.md).

| Capture | What was actually observed |
| --- | --- |
| [Original rollback refusal, desktop](original-rollback-refusal-1440.png) | The original supported rollback question falsely refuses at threshold -8. GET-only capture of an existing saved query; no new execution. Main final connected suite failed at all three viewports. |
| [Factual answer, desktop](diagnostic-answer-1440.png) | Supplemental actual uploaded Anika fixture, reader identity and saved answer. This narrow diagnostic does not pass the original journey. |
| [Source, mobile](diagnostic-source-390.png), [tablet](diagnostic-source-768.png), [desktop](diagnostic-source-1440.png) | Exact saved full-paragraph span [0,205) highlighted inside the canonical source, with version/hash. Mobile drawer scrolls vertically; no horizontal clipping observed. Narrow/nonzero Unicode offsets have separate unit evidence. |
| [Reader error, mobile](diagnostic-reader-error-390.png), [desktop](diagnostic-reader-error-1440.png) | Actual persisted missing-model HTTP503, presented as an error with its historical threshold0 rather than a successful refusal. Fault injection is explicit. |
| [Connection failure, mobile](diagnostic-outage-390.png) | Deliberately interrupted network request shows Retry and explicit sample entry, with no automatic successful sample substitution. |
| [Sample source, mobile](sample-source-390.png), [sample overview, desktop](sample-overview-1440.png) | Offline interactive sample data. Sample journeys assert zero backend/provider/external requests. |

All three established sizes were exercised: 390×844, 768×1024 and 1440×900.
Inspecting a screenshot does not establish every downstream interaction. Final
full version/workflow actions were blocked by the earlier rollback answer failure;
the prior milestone's passing journey remains historical evidence.
