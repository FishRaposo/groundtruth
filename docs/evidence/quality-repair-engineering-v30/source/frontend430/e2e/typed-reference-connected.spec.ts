import { expect, test, type APIRequestContext } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";

type Row = Record<string, unknown>;
type Range = { start: number; end: number };
interface InputFile {
  logical_id: string; file: string; role: "procedure" | "retain" | "discard";
  title: string; version: number; upload_bytes: number; upload_sha256: string;
  canonical_sha256: string; expected_reference_plan: Row | null;
}
interface Inputs {
  schema: string; purpose: string; exclude_from_future_blind: boolean; policy: string;
  files: InputFile[]; question: string; copied_extent: Range; disclosure: string;
  unsupported_question: string; unresolved_question: string;
  replacement: { file: string; version: number; upload_bytes: number; upload_sha256: string; canonical_sha256: string; copied_extent: Range };
}
interface Seed {
  api_url: string; seed_status: string;
  principals: Record<string, { api_key: string; workspace_id: string; role: string }>;
  typed_connected_v360: {
    schema: string; input_manifest_sha256: string; policy: string;
    projects: Record<string, { principal_alias: string; documents: Record<string, { document_id: string; version: number; content_hash: string }> }>;
  };
}
interface QueryDTO {
  id: string; question: string; answer: string | null; outcome: string; refused: boolean;
  sources: { document_id: string; document_version: number; content_hash: string; quoted_text: string; citation_index: number; source_status: string; answer_spans: { start: number; end: number; text: string }[] }[];
  provenance: { answer_selection: Row };
  retrieval_trace: Row;
}
const row = (value: unknown): Row => { expect(value).toBeTruthy(); expect(typeof value).toBe("object"); expect(Array.isArray(value)).toBe(false); return value as Row; };
const rows = (value: unknown): Row[] => { expect(Array.isArray(value)).toBe(true); return (value as unknown[]).map(row); };
const hash = (value: string | Buffer) => createHash("sha256").update(value).digest("hex");
const slice = (value: string, range: Range) => Array.from(value).slice(range.start, range.end).join("");
const PROFILE = {
  contract: "evidence-profile-v4", proposal_profile: "qa_plus_source_patterns_v1", role_scope_policy: "ordinary_session_activity_v1",
  origin_contract: "proposal-origin-v1", role_policy_contract: "ordinary-session-activity-role-v1",
  pattern_registry_contract: "typed-source-patterns-v1", pattern_limits: { per_source_requirement: 3, per_requirement: 16 },
  procedure_verification_profile: "source_declared_procedure_copy_v1",
  source_context_policy: "scoped_note_context_v2", source_context_contract: "source-note-context-v2",
};

// Fail closed during execution. --list discovers tests without reading secrets.
// Never use page.route/fulfill or successful endpoint doubles in this suite.
test.use({ trace: "off", screenshot: "off", video: "off" });
test("typed context references: real ingestion lineage, NLI, exact binding, disclosure, refusal and saved history", async ({ page, request }, info) => {
  const manifestPath = process.env.GROUNDTRUTH_SEED_MANIFEST;
  const inputsPath = process.env.GROUNDTRUTH_TYPED_INPUTS;
  expect(Boolean(manifestPath), "Private seed manifest path is required").toBe(true);
  expect(Boolean(inputsPath), "Public engineering input manifest path is required").toBe(true);
  expect(process.env.GROUNDTRUTH_EXPECTED_CONTEXT_POLICY).toBe("scoped_note_context_v2");
  const marginInput = process.env.GROUNDTRUTH_EXPECTED_SUPPORT_MARGIN ?? "0";
  const expectedMargin = Number(marginInput);
  expect(marginInput.trim(), "Expected support margin cannot be empty").not.toBe("");
  expect(Number.isFinite(expectedMargin) && expectedMargin >= 0 && expectedMargin <= 4, "Expected support margin must be finite and between 0 and 4").toBe(true);
  const manifestBytes = readFileSync(inputsPath!);
  const inputs: Inputs = JSON.parse(manifestBytes.toString("utf8"));
  const seed: Seed = JSON.parse(readFileSync(manifestPath!, "utf8"));
  expect(["http://127.0.0.1:8401", "http://127.0.0.1:8402"]).toContain(seed.api_url);
  expect(seed.seed_status).toBe("complete");
  expect(inputs).toMatchObject({ schema: "typed-connected-inputs-v360", exclude_from_future_blind: true, policy: "scoped_note_context_v2" });
  expect(seed.typed_connected_v360).toMatchObject({ schema: "typed-connected-private-seed-v360", input_manifest_sha256: hash(manifestBytes), policy: "scoped_note_context_v2" });
  const width = String(info.project.use.viewport!.width);
  const cohort = seed.typed_connected_v360.projects[width];
  expect(cohort, "Each viewport needs its own owner/workspace and three source documents").toBeTruthy();
  const cohorts = ["390", "768", "1440"].map(viewport => seed.typed_connected_v360.projects[viewport]);
  expect(cohorts.every(Boolean)).toBe(true);
  expect(new Set(cohorts.map(project => project.principal_alias)).size).toBe(3);
  expect(new Set(cohorts.map(project => seed.principals[project.principal_alias].workspace_id)).size).toBe(3);
  expect(new Set(cohorts.flatMap(project => Object.values(project.documents).map(document => document.document_id))).size).toBe(9);
  const principal = seed.principals[cohort.principal_alias];
  expect(principal.role).toBe("owner");
  const key = principal.api_key;
  expect(typeof key).toBe("string");
  expect(key.length).toBeGreaterThan(15);
  const headers = { "X-API-Key": key };
  const directory = path.dirname(inputsPath!);
  const bodyFor = (file: string) => readFileSync(path.join(directory, file)).toString("utf8");
  for (const entry of [...inputs.files, inputs.replacement]) {
    const raw = readFileSync(path.join(directory, entry.file));
    expect(raw.length).toBe(entry.upload_bytes);
    expect(hash(raw)).toBe(entry.upload_sha256);
    expect(hash(bodyFor(entry.file))).toBe(entry.canonical_sha256);
  }
  expect(inputs.files).toHaveLength(3);
  expect(new Set(inputs.files.map(entry => entry.role))).toEqual(new Set(["procedure", "retain", "discard"]));
  const main = inputs.files.find(entry => entry.role === "procedure")!;
  const sourceId = (entry: InputFile) => cohort.documents[entry.logical_id].document_id;
  const allIDs = inputs.files.map(sourceId).sort();
  expect(new Set(allIDs).size).toBe(3);
  const failures: string[] = [];
  const redact = (message: string) => message.replaceAll(key, "[redacted]");
  page.on("pageerror", error => failures.push(redact(error.message)));
  page.on("console", message => { if (message.type() === "error") failures.push(redact(message.text())); });
  page.on("request", req => { const url = new URL(req.url()); if (!["127.0.0.1", "localhost"].includes(url.hostname)) failures.push(`External request: ${url.origin}${url.pathname}`); });
  const safeAttach = async (name: string, value: unknown) => {
    const text = JSON.stringify(value, null, 2);
    expect(text.includes(key), "Evidence must never contain the disposable key").toBe(false);
    expect(text).not.toContain('"api_key"');
    await info.attach(name, { contentType: "application/json", body: Buffer.from(text) });
  };
  const get = async (client: APIRequestContext, endpoint: string) => {
    const response = await client.get(seed.api_url + endpoint, { headers });
    expect(response.ok(), `Real authorized GET ${endpoint} must succeed`).toBe(true);
    return await response.json();
  };
  // Readiness warms the real pinned reader/classifier. Runtime constants below
  // are independent expectations, not acceptance of the server's own profile.
  const ready = await get(request, "/api/health/ready");
  expect(ready.checks).toMatchObject({ reader: "ok", evidence_support: "ok" });
  const health = await get(request, "/api/health");
  const expectedEmbedding = process.env.GROUNDTRUTH_TYPED_EMBEDDING_MODE;
  expect(["deterministic", "local"]).toContain(expectedEmbedding);
  expect(health.runtime).toMatchObject({ persistence: "sqlite", ingestion_mode: "inline", generation_mode: "extractive", authentication: "api-key", embedding: { mode: expectedEmbedding }, evidence_profile: PROFILE,
    answer_selection: { mode: "reader", model: "deepset/roberta-base-squad2", revision: "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4", threshold: 4, readiness: "ready" },
    evidence_support: { mode: "local_nli", model: "cross-encoder/nli-deberta-v3-small", revision: "70de96bd327ef95839a8bd9f6299875cae396433", readiness: "ready", minimum_entailment_margin: expectedMargin, max_pair_tokens: 512, device: "cpu" },
  });
  await safeAttach("typed-runtime", { qualification: "Observed local engineering runtime; not model quality", runtime: health.runtime });
  const snapshot = async (id: string, version: number, body: string, status: string) => {
    const observed = await get(request, `/api/v1/documents/${id}/versions/${version}`);
    expect(observed).toMatchObject({ document_id: id, version_number: version, normalized_content: body, content_hash: hash(body), source_status: status });
    return observed;
  };
  for (const entry of inputs.files) {
    expect(cohort.documents[entry.logical_id]).toMatchObject({ version: 1, content_hash: entry.canonical_sha256 });
    await snapshot(sourceId(entry), 1, bodyFor(entry.file), "current");
  }
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("groundtruth.typed.v360")) {
      localStorage.setItem("groundtruth.source.v1", "sample");
      sessionStorage.clear(); sessionStorage.setItem("groundtruth.typed.v360", "1");
    }
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/chat");
  await expect(page).toHaveTitle(/GroundTruth/i);
  await page.getByRole("button", { name: "Connection", exact: true }).click();
  // Avoid putting a credential in a fill action's call log. Recording is off.
  await page.getByLabel("API key", { exact: true }).evaluate((element, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, key);
  await page.getByRole("button", { name: "Connect application" }).click();
  await expect(page.getByText("Connected local application", { exact: true })).toBeVisible();
  expect(new URL(page.url()).origin).toBe("http://127.0.0.1:3506");
  const answer = page.getByLabel("Answer and evidence");
  const layout = async () => {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
    await expect(page.locator("nextjs-portal, vite-error-overlay, #webpack-dev-server-client-overlay")).toHaveCount(0);
    const navigation = page.getByRole("link", { name: "Documents", exact: true });
    await navigation.scrollIntoViewIfNeeded();
    const bounds = await navigation.boundingBox();
    expect(bounds).toBeTruthy(); expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(Number(width) + 1);
  };
  const shot = async (label: string) => {
    const output = process.env.GROUNDTRUTH_SCREENSHOTS;
    expect(Boolean(output), "Root must provide a safe screenshot directory").toBe(true);
    await mkdir(output!, { recursive: true });
    expect(page.url().includes(key)).toBe(false);
    await page.screenshot({ path: path.join(output!, `typed-${label}-${width}.png`), fullPage: false });
  };
  const ask = async (question: string) => {
    await page.getByRole("button", { name: "New conversation" }).click();
    await expect(page).not.toHaveURL(/query=/);
    await page.getByRole("combobox", { name: "Document scope", exact: true }).selectOption("");
    await expect.poll(async () => page.getByRole("combobox", { name: "Document scope", exact: true }).locator("option").evaluateAll(elements => elements.map(element => (element as HTMLOptionElement).value).filter(Boolean).sort()), { message: "Loaded cohort may access exactly its own three notes", timeout: 30000 }).toEqual(allIDs);
    await page.getByRole("combobox", { name: "Retrieval method", exact: true }).selectOption("keyword");
    await page.getByLabel("Stream the actual answer (SSE)").setChecked(false);
    await page.getByLabel("What do you need to know?").fill(question);
    const completed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/queries" && response.request().method() === "POST");
    await page.getByRole("button", { name: "Ask question", exact: true }).click();
    const response = await completed;
    expect(new URL(response.url()).origin, "Compiled frontend API target must match the private seed manifest").toBe(seed.api_url);
    expect(response.ok(), "Actual query POST must succeed without sample substitution").toBe(true);
    const sent = response.request().postDataJSON();
    expect(sent).toMatchObject({ question, retrieval_method: "keyword", top_k: 5 });
    expect(sent.document_ids ?? null).toBeNull();
    const posted = await response.json() as QueryDTO;
    await expect(page).toHaveURL(new RegExp(`query=${posted.id}`));
    const saved = await get(request, `/api/queries/${posted.id}`) as QueryDTO;
    expect(saved).toEqual(posted);
    await safeAttach(`typed-query-${posted.id}`, { qualification: inputs.purpose, viewport: info.project.use.viewport, request: sent, response: saved });
    return saved;
  };
  const verify = async (query: QueryDTO, body: string, version: number, extent: Range) => {
    expect(query).toMatchObject({ question: inputs.question, outcome: "completed", refused: false });
    expect(query.answer).toContain(slice(body, extent));
    expect(query.answer).toContain(inputs.disclosure);
    expect(query.answer).toMatch(/^Source extracts with declared activity-scope interpretation:/);
    expect(new Set(query.sources.map(source => source.document_id))).toEqual(new Set([sourceId(main)]));
    for (const source of query.sources) {
      expect(source).toMatchObject({ document_version: version, content_hash: hash(body), source_status: "current" });
      expect(body).toContain(source.quoted_text);
      for (const span of source.answer_spans) expect(slice(source.quoted_text, span)).toBe(span.text);
      const actualSource = await get(request, `/api/queries/${query.id}/sources/${source.citation_index}`);
      expect(actualSource).toMatchObject({ document_id: sourceId(main), document_version: version, content_hash: source.content_hash, quoted_text: source.quoted_text, passage: source.quoted_text });
    }
    const selection = query.provenance.answer_selection;
    expect(selection.evidence_profile).toEqual(PROFILE);
    expect(row(selection.presentation_verification).status).toBe("verified");
    const requirements = rows(selection.requirements); expect(requirements).toHaveLength(1);
    expect(requirements[0].status).toBe("supported");
    const proof = row(requirements[0].procedure_completeness);
    expect(proof).toMatchObject({ contract: "complete-immutable-procedure-v3", document_id: sourceId(main), document_version: version, content_hash: hash(body), extent });
    const units = rows(proof.proof_units);
    expect(new Set(units.map(unit => unit.verification_method))).toEqual(new Set(["nli_entailment", "exact_source_structure", "exact_source_copy"]));
    for (const kind of ["namespace", "applicability"]) expect(units.find(unit => unit.kind === kind)).toMatchObject({ verification_method: "nli_entailment", supported: true, label: "entailment" });
    for (const unit of units) {
      expect(unit.supported).toBe(true);
      if (unit.verification_method === "nli_entailment") {
        expect(unit.label).toBe("entailment");
        expect(Number.isFinite(unit.entailment_margin)).toBe(true);
        expect(unit.entailment_margin as number).toBeGreaterThanOrEqual(expectedMargin);
        expect(unit.pair_tokens as number).toBeGreaterThan(0);
      } else for (const field of ["label", "logits", "entailment_margin", "pair_tokens"]) expect(unit).not.toHaveProperty(field);
    }
    const certificate = row(proof.output_certificate);
    expect(certificate).toMatchObject({ contract: "procedure-output-cover-v4", answer_sha256: hash(query.answer!), instruction_range: extent, request_binding: { question: inputs.question } });
    expect(slice(query.answer!, certificate.answer_range as Range)).toBe(slice(body, extent));
    const inventory = row(proof.condition_exclusion_inventory);
    expect(inventory.contract).toBe("procedure-condition-exclusion-inventory-v3");
    expect(certificate.condition_exclusion_inventory).toEqual(inventory);
    const exclusions = rows(inventory.exclusions); expect(exclusions).toHaveLength(2);
    expect(exclusions.map(exclusion => row(exclusion.source_identity).document_id).sort()).toEqual(inputs.files.filter(file => file.role !== "procedure").map(sourceId).sort());
    for (const exclusion of exclusions) {
      const entry = inputs.files.find(file => sourceId(file) === row(exclusion.source_identity).document_id)!;
      expect(row(exclusion.source_identity)).toMatchObject({ document_version: 1, content_hash: entry.canonical_sha256 });
      const scope = row(exclusion.condition_scope);
      expect(scope).toMatchObject({ contract: "procedure-condition-scope-v3", verification_method: "contextual_source_reading_nli_and_exact_reference", obligation_plan: { contract: "source-note-obligation-plan-v2", mandatory_nli_count: 22, mandatory_exact_reference_count: 1, mandatory_obligation_count: 23 } });
      const reading = row(scope.context_reading);
      expect(reading).toMatchObject({ contract: "source-note-context-v2", grammar: "scoped-note-grammar-v2", source_body: bodyFor(entry.file), source_body_hash: entry.canonical_sha256, disclosure: inputs.disclosure });
      const checks = rows(scope.semantic_checks); expect(checks).toHaveLength(22);
      expect(new Set(checks.map(check => check.name)).size).toBe(22);
      for (const check of checks) {
        expect(check.verification_method).toBe("nli_entailment");
        const assessment = row(check.assessment);
        expect(assessment).toMatchObject({ supported: true, label: "entailment" });
        expect(Number.isFinite(assessment.entailment_margin)).toBe(true);
        expect(assessment.entailment_margin as number).toBeGreaterThanOrEqual(expectedMargin);
        expect(assessment.pair_tokens as number).toBeGreaterThan(0);
        expect(assessment.pair_tokens as number).toBeLessThanOrEqual(512);
        const logits = assessment.logits as number[]; expect(logits).toHaveLength(3);
        expect(logits.every(Number.isFinite)).toBe(true);
        expect(assessment.entailment_margin as number).toBeCloseTo(logits[1] - Math.max(logits[0], logits[2]), 5);
        expect(slice(bodyFor(entry.file), check.premise_range as Range)).toBe(row(check.pair).premise);
      }
      const exact = rows(scope.reference_obligations); expect(exact).toHaveLength(1);
      expect(exact[0]).toMatchObject({ name: "card_reference_linkage", contract: "context-reference-structure-v1", verification_method: "exact_context_reference_structure", result: "bound" });
      expect(exact[0].reference_plan).toEqual(entry.expected_reference_plan);
      for (const name of ["assessment", "label", "logits", "entailment_margin", "pair_tokens", "pair", "score"]) expect(exact[0]).not.toHaveProperty(name);
    }
    await expect(answer.locator(".gt-answer-text")).toContainText(slice(body, extent));
    await expect(answer.locator(".gt-answer-text")).toContainText(inputs.disclosure);
    const evidence = answer.getByLabel("Answer selection evidence");
    await expect(evidence).toContainText("Exact instruction coverage verified", { timeout: 30000 });
    await expect(evidence).toContainText("Recorded output hash: matched");
    const context = evidence.getByRole("region", { name: "Context reading", exact: true });
    await expect(context).toContainText("This is a policy interpretation, separate from recorded NLI support");
    await expect(context).toContainText("Opposing card dispositions remain unresolved");
    const exactRegion = context.getByRole("region", { name: "Recorded context-reference structure" });
    await expect(exactRegion).toContainText("without establishing physical identity, existence or successful execution");
    const summaries = exactRegion.locator("summary").filter({ hasText: /^Recorded typed reference binding/ });
    await expect(summaries).toHaveCount(2);
    for (let index = 0; index < 2; index++) {
      await summaries.nth(index).focus(); await page.keyboard.press("Enter");
      const details = summaries.nth(index).locator("..");
      await expect(details).toHaveAttribute("open", "");
      await expect(details).toContainText("22 recorded NLI checks and 1 exact reference obligation");
      await expect(details).toContainText("Reference binding method: exact_context_reference_structure");
      await expect(details).toContainText("result: bound");
      await expect(details).toContainText("Guard: and");
      await expect(details).toContainText("cover of card");
      await expect(details).not.toContainText(/logits|margin:|pair tokens:/i);
      const completePlan = details.locator("summary").filter({ hasText: "Complete typed reference plan" });
      await completePlan.focus(); await page.keyboard.press("Enter");
      await expect(completePlan.locator("..").locator("pre")).toContainText('"contract": "context-reference-structure-v1"');
      await page.keyboard.press("Enter");
    }
    await exactRegion.scrollIntoViewIfNeeded(); await shot(`proof-v${version}`);
    const clauses = context.locator("summary").filter({ hasText: /^Recorded literal clauses and references/ });
    await expect(clauses).toHaveCount(2);
    for (let index = 0; index < 2; index++) {
      await clauses.nth(index).focus(); await page.keyboard.press("Enter");
      const note = clauses.nth(index).locator("..");
      const sourceSummary = note.locator("summary").filter({ hasText: "Recorded complete context source" });
      await sourceSummary.focus(); await page.keyboard.press("Enter");
      const renderedBody = await sourceSummary.locator("..").locator("pre").textContent();
      expect(inputs.files.filter(file => file.role !== "procedure").map(file => bodyFor(file.file))).toContain(renderedBody);
      await expect(note).toContainText("postponed audit disposition");
      await expect(note).toContainText("Cards without that combination");
      const nli = note.locator("summary").filter({ hasText: "Recorded contextual NLI checks" });
      await nli.focus(); await page.keyboard.press("Enter");
      await expect(nli.locator("..")).toContainText("Recorded NLI method: nli_entailment");
      await expect(nli.locator("..")).toContainText("Recorded NLI logits (contradiction, entailment, neutral)");
      await expect(nli.locator("..").locator("li")).toHaveCount(22);
    }
    await clauses.first().scrollIntoViewIfNeeded(); await shot(`scoped-notes-v${version}`);
    await layout();
  };
  const original = await ask(inputs.question);
  const savedURL = page.url();
  await verify(original, bodyFor(main.file), 1, inputs.copied_extent);
  const citation = answer.locator(".gt-source-card").first();
  await citation.focus(); await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Canonical quoted evidence")).toHaveText(original.sources[0].quoted_text);
  await expect(dialog.locator("mark[data-answer-span=true]").first()).toBeVisible();
  for (let step = 0; step < 6; step++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  await dialog.getByText("Immutable source identity", { exact: true }).click();
  await expect(dialog).toContainText(main.canonical_sha256);
  await shot("source-v1"); await layout();
  await page.keyboard.press("Escape"); await expect(citation).toBeFocused();
  await page.reload();
  await expect(answer.locator(".gt-answer-text")).toContainText(inputs.disclosure, { timeout: 30000 });
  expect(await get(request, `/api/queries/${original.id}`)).toEqual(original);
  const history = await get(request, "/api/queries?limit=100");
  expect(rows(history.queries).some(query => query.id === original.id)).toBe(true);
  for (const [label, question] of [["unsupported", inputs.unsupported_question], ["unresolved-audit", inputs.unresolved_question]]) {
    const refused = await ask(question);
    expect(refused).toMatchObject({ outcome: "refused", refused: true, answer: null, sources: [] });
    await expect(answer.locator(".gt-refusal")).toBeVisible();
    await expect(answer.locator(".gt-source-card")).toHaveCount(0);
    await expect(answer).not.toContainText("Exact instruction coverage verified");
    await shot(label); await layout();
  }
  // Each viewport has its own cohort: this real version POST cannot change
  // another viewport's initial snapshot or its acceptance preconditions.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const card = page.getByRole("article").filter({ has: page.getByRole("heading", { name: main.title, exact: true }) });
  await card.getByRole("button", { name: "Versions & evidence" }).click();
  const versions = page.getByRole("dialog");
  await versions.getByLabel("Replacement file").setInputFiles({ name: inputs.replacement.file, mimeType: "text/plain", buffer: readFileSync(path.join(directory, inputs.replacement.file)) });
  const replaced = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/documents/${sourceId(main)}/versions` && response.request().method() === "POST");
  await versions.getByRole("button", { name: "Submit new version" }).click();
  expect((await replaced).ok(), "Real version upload must publish the new body").toBe(true);
  await expect(versions).not.toBeVisible({ timeout: 60000 });
  await expect(card).toContainText("Version 2");
  await snapshot(sourceId(main), 1, bodyFor(main.file), "superseded");
  await snapshot(sourceId(main), 2, bodyFor(inputs.replacement.file), "current");
  const publishedVersions = await get(request, `/api/v1/documents/${sourceId(main)}/versions`);
  expect(rows(publishedVersions).map(version => version.version_number).sort()).toEqual([1, 2]);
  await card.getByRole("button", { name: "Versions & evidence" }).click();
  await versions.getByRole("button", { name: "Compare previous and current" }).click();
  await expect(versions.getByLabel("Version comparison")).toContainText("Place two tokens");
  await versions.getByRole("button", { name: "Inspect passage v1" }).click();
  await expect(versions.getByLabel("Version snapshot")).toContainText("Place one token");
  await versions.getByRole("button", { name: "Inspect passage v2" }).click();
  await expect(versions.getByLabel("Version snapshot")).toContainText("Place two tokens");
  await shot("version-history"); await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  const updated = await ask(inputs.question);
  await verify(updated, bodyFor(inputs.replacement.file), 2, inputs.replacement.copied_extent);
  await page.goto(savedURL); await page.reload();
  await expect(answer.locator(".gt-answer-text")).toContainText("Place one token", { timeout: 30000 });
  await expect(answer.locator(".gt-answer-text")).not.toContainText("Place two tokens");
  const historical = await get(request, `/api/queries/${original.id}`) as QueryDTO;
  expect(historical.answer).toBe(original.answer);
  expect(historical.provenance).toEqual(original.provenance);
  expect(historical.sources.every(source => source.document_version === 1 && source.content_hash === main.canonical_sha256 && source.source_status === "superseded")).toBe(true);
  await answer.locator(".gt-source-card").first().click();
  await expect(page.getByRole("dialog")).toContainText("superseded");
  await expect(page.getByRole("dialog")).toContainText("Version 1");
  await shot("saved-history"); await page.keyboard.press("Escape");
  await layout();
  await safeAttach("typed-history-observation", { qualification: inputs.purpose, viewport: info.project.use.viewport, original_query: original.id, updated_query: updated.id, historical_query: historical, input_manifest_sha256: hash(manifestBytes) });
  expect(failures).toEqual([]);
});
