import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";

interface DemoFile {
  file: string;
  source_family: string;
  role: "initial" | "replacement";
  version: number;
  structure: "numbered" | "declared_paragraphs";
  upload_bytes: number;
  upload_sha256: string;
  canonical_sha256: string;
  copied_extent: { start: number; end: number };
  question: string;
}
interface ProofUnit {
  kind: string;
  verification_method: string;
  supported: boolean;
  label?: string;
  logits?: number[];
  entailment_margin?: number;
  pair_tokens?: number;
}
interface SavedQuery {
  id: string;
  question: string;
  answer: string | null;
  outcome: string;
  refused: boolean;
  sources: {
    document_id: string;
    document_version: number;
    content_hash: string;
    quoted_text: string;
    source_status: string;
    citation_index: number;
  }[];
  provenance: { answer_selection: {
    evidence_profile: {
      contract: string;
      proposal_profile: string;
      procedure_verification_profile: string;
    };
    presentation_verification: { status: string };
    requirements: { status: string; procedure_completeness: {
      contract: string;
      structure: string;
      document_id: string;
      document_version: number;
      content_hash: string;
      extent: { start: number; end: number };
      proof_units: ProofUnit[];
      output_certificate: {
        contract: string;
        renderer: string;
        request_binding: { question: string };
        instruction_range: { start: number; end: number };
        answer_range: { start: number; end: number };
        answer_sha256: string;
      };
    } }[];
  } };
}

const manifestPath = process.env.GROUNDTRUTH_SEED_MANIFEST;
const assetRoot = path.resolve(__dirname, "../../api/app/portfolio/assets/procedure-copy-demo");
const demo: { files: DemoFile[]; unsupported_qualifier_question: string } = JSON.parse(
  readFileSync(path.join(assetRoot, "manifest.json"), "utf8"),
);
const sha256 = (value: string | Buffer) => createHash("sha256").update(value).digest("hex");
const uploadBytes = (entry: DemoFile) => readFileSync(path.join(assetRoot, entry.file));
// These assets contain only LF and one final newline. Do not trim retained spaces.
const bodyFor = (entry: DemoFile) => uploadBytes(entry).toString("utf8").replace(/\n$/, "");
const copiedText = (entry: DemoFile) => Array.from(bodyFor(entry)).slice(entry.copied_extent.start, entry.copied_extent.end).join("");

test.skip(!manifestPath, "Requires the private disposable API seed manifest and the actual combined profile; no successful mocks.");
// Auth actions and HTTP headers contain the private disposable key. Explicit
// post-connect screenshots below are safe; recording authentication is not.
test.use({ trace: "off", screenshot: "off", video: "off" });

test("combined procedure copy: real upload, exact scope, NLI/exact evidence, refusal and version history", async ({ page, request }, info) => {
  test.setTimeout(300000);
  const seed: { api_url: string; principals: Record<string, { api_key: string }> } = JSON.parse(readFileSync(manifestPath!, "utf8"));
  expect(["127.0.0.1", "localhost"]).toContain(new URL(seed.api_url).hostname);
  const key = seed.principals["admin-a"].api_key;
  const headers = { "X-API-Key": key };
  const initial = demo.files.filter((entry) => entry.role === "initial");
  const replacement = demo.files.find((entry) => entry.role === "replacement")!;
  expect(initial).toHaveLength(2);
  for (const entry of demo.files) {
    expect(uploadBytes(entry).length).toBe(entry.upload_bytes);
    expect(sha256(uploadBytes(entry))).toBe(entry.upload_sha256);
    expect(sha256(bodyFor(entry))).toBe(entry.canonical_sha256);
  }
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message.replaceAll(key, "[redacted]")));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text().replaceAll(key, "[redacted]"));
  });
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) errors.push(`External request: ${url.origin}${url.pathname}`);
  });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("groundtruth.combined.initialized")) {
      localStorage.setItem("groundtruth.source.v1", "sample");
      sessionStorage.clear();
      sessionStorage.setItem("groundtruth.combined.initialized", "1");
    }
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/chat");
  await page.getByRole("button", { name: "Connection", exact: true }).click();
  // Use the native setter without placing the secret in a fill action call log.
  await page.getByLabel("API key", { exact: true }).evaluate((element, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }, key);
  await page.getByRole("button", { name: "Connect application" }).click();
  await expect(page.getByText("Connected local application", { exact: true })).toBeVisible();

  const shot = async (label: string) => {
    const directory = process.env.GROUNDTRUTH_SCREENSHOTS;
    if (!directory) return;
    await mkdir(directory, { recursive: true });
    await page.screenshot({ path: path.join(directory, `combined-${label}-${info.project.use.viewport?.width}.png`), fullPage: false });
  };
  const fits = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const filename = (entry: DemoFile) => `combined-${info.project.name}-${Date.now()}-${entry.file}`;
  const uploads = initial.map((entry) => ({ entry, name: filename(entry) }));
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await page.getByLabel("Choose documents").setInputFiles(uploads.map(({ entry, name }) => ({
    name, mimeType: "text/plain", buffer: uploadBytes(entry),
  })));
  const uploadedResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/documents/upload" && response.request().method() === "POST");
  await page.getByRole("button", { name: "Upload & ingest" }).click();
  const uploaded = await uploadedResponse;
  expect(uploaded.ok(), "Actual document upload must succeed").toBe(true);
  const uploadedBody: { documents: { id: string; title: string }[] } = await uploaded.json();
  expect(uploadedBody.documents).toHaveLength(2);
  const documents = uploads.map(({ entry, name }) => {
    const published = uploadedBody.documents.find((document) => document.title === name);
    expect(published, `Upload must return the new ${entry.file} identity`).toBeTruthy();
    return { entry, name, id: published!.id };
  });
  const cardFor = (name: string) => page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });
  const verifySnapshot = async (id: string, entry: DemoFile, status: string) => {
    const response = await request.get(`${seed.api_url}/api/v1/documents/${id}/versions/${entry.version}`, { headers });
    expect(response.ok(), "Actual authorized immutable snapshot must be available").toBe(true);
    const snapshot = await response.json();
    expect(snapshot.normalized_content).toBe(bodyFor(entry));
    expect(snapshot.content_hash).toBe(entry.canonical_sha256);
    expect(snapshot.source_status).toBe(status);
  };
  for (const { entry, name, id } of documents) {
    await expect(cardFor(name)).toContainText("ready", { timeout: 60000 });
    await verifySnapshot(id, entry, "current");
  }
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  const answer = page.getByLabel("Answer and evidence");
  const records: { id: string; document_id: string; version: number; outcome: string }[] = [];
  const ask = async (question: string, id: string, stream: boolean) => {
    await page.getByRole("button", { name: "New conversation" }).click();
    await expect(page).not.toHaveURL(/query=/);
    await expect(page.getByRole("combobox", { name: "Conversation", exact: true })).not.toHaveValue("");
    await page.getByRole("combobox", { name: "Document scope", exact: true }).selectOption(id);
    await page.getByRole("combobox", { name: "Retrieval method", exact: true }).selectOption("keyword");
    await page.getByLabel("Stream the actual answer (SSE)").setChecked(stream);
    await page.getByLabel("What do you need to know?").fill(question);
    const before = page.url();
    const sent = page.waitForRequest((req) => new URL(req.url()).pathname === (stream ? "/api/queries/stream" : "/api/queries") && req.method() === "POST");
    await page.getByRole("button", { name: "Ask question", exact: true }).click();
    const submitted = (await sent).postDataJSON();
    expect(submitted.document_ids).toEqual([id]);
    expect(submitted.question).toBe(question);
    await expect(page).not.toHaveURL(before, { timeout: 90000 });
    expect(page.url().includes(key)).toBe(false);
    const queryID = new URL(page.url()).searchParams.get("query");
    expect(queryID).toBeTruthy();
    const response = await request.get(`${seed.api_url}/api/queries/${queryID}`, { headers });
    expect(response.ok(), "Actual saved query must be readable").toBe(true);
    return await response.json() as SavedQuery;
  };
  const verifyCompleted = async (record: SavedQuery, entry: DemoFile, id: string) => {
    expect(record.outcome).toBe("completed");
    expect(record.refused).toBe(false);
    expect(record.question).toBe(entry.question);
    expect(record.answer).toContain(copiedText(entry));
    expect(new Set(record.sources.map((source) => source.document_id))).toEqual(new Set([id]));
    for (const source of record.sources) {
      expect(source.document_version).toBe(entry.version);
      expect(source.content_hash).toBe(entry.canonical_sha256);
      expect(bodyFor(entry)).toContain(source.quoted_text);
    }
    const selection = record.provenance.answer_selection;
    expect(selection.evidence_profile).toMatchObject({ contract: "evidence-profile-v2", proposal_profile: "qa_plus_source_patterns_v1", procedure_verification_profile: "source_declared_procedure_copy_v1" });
    expect(selection.presentation_verification.status).toBe("verified");
    expect(selection.requirements).toHaveLength(1);
    const proof = selection.requirements[0].procedure_completeness;
    expect(selection.requirements[0].status).toBe("supported");
    expect(proof).toMatchObject({ contract: "complete-immutable-procedure-v3", structure: entry.structure, document_id: id, document_version: entry.version, content_hash: entry.canonical_sha256, extent: entry.copied_extent });
    expect(new Set(proof.proof_units.map((unit) => unit.verification_method))).toEqual(new Set(["nli_entailment", "exact_source_structure", "exact_source_copy"]));
    for (const kind of ["namespace", "applicability"]) expect(proof.proof_units.find((unit) => unit.kind === kind)).toMatchObject({ verification_method: "nli_entailment", supported: true, label: "entailment" });
    for (const unit of proof.proof_units) {
      expect(unit.supported).toBe(true);
      if (unit.verification_method === "nli_entailment") {
        expect(unit.label).toBe("entailment");
        expect(Number.isFinite(unit.entailment_margin)).toBe(true);
        expect(unit.pair_tokens).toBeGreaterThan(0);
      } else for (const field of ["label", "logits", "entailment_margin", "pair_tokens"]) expect(unit).not.toHaveProperty(field);
    }
    const certificate = proof.output_certificate;
    expect(certificate).toMatchObject({ contract: "procedure-output-cover-v1", renderer: "extractive-answer-v1", request_binding: { question: entry.question }, instruction_range: entry.copied_extent, answer_sha256: sha256(record.answer!) });
    expect(Array.from(record.answer!).slice(certificate.answer_range.start, certificate.answer_range.end).join("")).toBe(copiedText(entry));
    await expect(answer.locator(".gt-answer-text")).toContainText(copiedText(entry));
    const evidence = answer.getByLabel("Answer selection evidence");
    await expect(evidence.getByRole("heading", { name: "Source-declared procedure copy", exact: true })).toBeVisible();
    await expect(evidence).toContainText("Exact instruction coverage verified", { timeout: 30000 });
    await expect(evidence).toContainText("NLI-supported subject and applicability");
    await expect(evidence).toContainText("exact_source_structure and exact_source_copy");
    await expect(evidence).toContainText("Recorded output hash: matched");
    await expect(evidence).not.toContainText("Full source extent verified");
    await expect(answer.getByRole("region", { name: "Request coverage" })).toContainText("1 of 1 requirements supported");
    records.push({ id: record.id, document_id: id, version: entry.version, outcome: record.outcome });
    await fits();
  };

  const saved = new Map<string, { url: string; record: SavedQuery }>();
  for (const { entry, id } of documents) {
    const record = await ask(entry.question, id, entry.structure === "declared_paragraphs");
    await verifyCompleted(record, entry, id);
    saved.set(id, { url: page.url(), record });
    await shot(entry.structure);
    const citation = answer.locator(".gt-source-card").first();
    await citation.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Canonical quoted evidence")).toHaveText(record.sources[0].quoted_text);
    await expect(dialog.locator("mark[data-answer-span=true]").first()).toBeVisible();
    await dialog.getByText("Immutable source identity", { exact: true }).click();
    await expect(dialog).toContainText(id);
    await expect(dialog).toContainText(entry.canonical_sha256);
    await shot(`${entry.structure}-source`);
    await fits();
    await page.keyboard.press("Escape");
    await expect(citation).toBeFocused();
    await page.reload();
    await verifyCompleted(record, entry, id);
  }

  const cedar = documents.find(({ entry }) => entry.structure === "numbered")!;
  const refused = await ask(demo.unsupported_qualifier_question, cedar.id, false);
  expect(refused.outcome).toBe("refused");
  expect(refused.refused).toBe(true);
  expect(refused.answer).toBeNull();
  expect(refused.sources).toHaveLength(0);
  await expect(answer.locator(".gt-refusal")).toBeVisible();
  await expect(answer.locator(".gt-source-card")).toHaveCount(0);
  await expect(answer).not.toContainText("Exact instruction coverage verified");
  await shot("unsupported-qualifier");

  const juniper = documents.find(({ entry }) => entry.structure === "declared_paragraphs")!;
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const card = cardFor(juniper.name);
  await card.getByRole("button", { name: "Versions & evidence" }).click();
  const history = page.getByRole("dialog");
  await expect(history).toContainText("Version 1");
  await history.getByLabel("Replacement file").setInputFiles({ name: replacement.file, mimeType: "text/plain", buffer: uploadBytes(replacement) });
  await history.getByRole("button", { name: "Submit new version" }).click();
  await expect(history).not.toBeVisible({ timeout: 60000 });
  await expect(card).toContainText("Version 2");
  await verifySnapshot(juniper.id, juniper.entry, "superseded");
  await verifySnapshot(juniper.id, replacement, "current");
  await card.getByRole("button", { name: "Versions & evidence" }).click();
  await history.getByRole("button", { name: "Compare previous and current" }).click();
  await expect(history.getByLabel("Version comparison")).toContainText("staging readiness result");
  await history.getByRole("button", { name: "Inspect passage v1" }).click();
  await expect(history.getByLabel("Version snapshot")).toContainText("staging health result");
  await history.getByRole("button", { name: "Inspect passage v2" }).click();
  await expect(history.getByLabel("Version snapshot")).toContainText("staging readiness result");
  await shot("version-history");
  await fits();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  const revised = await ask(replacement.question, juniper.id, false);
  await verifyCompleted(revised, replacement, juniper.id);
  await expect(answer.locator(".gt-answer-text")).not.toContainText("staging health result");
  await shot("updated-procedure");

  const original = saved.get(juniper.id)!;
  await page.goto(original.url);
  await expect(answer.locator(".gt-answer-text")).toContainText(copiedText(juniper.entry), { timeout: 30000 });
  await expect(answer.locator(".gt-answer-text")).not.toContainText("staging readiness result");
  await answer.locator(".gt-source-card").first().click();
  await expect(page.getByRole("dialog")).toContainText("superseded");
  await expect(page.getByRole("dialog")).toContainText("Version 1");
  await page.keyboard.press("Escape");
  await info.attach("combined-procedure-observation", { contentType: "application/json", body: Buffer.from(JSON.stringify({ scope: "Synthetic engineering workflow acceptance; not DEV/blind quality evidence", viewport: info.project.use.viewport, records, refused_query_id: refused.id, upload_hashes: demo.files.map(({ file, upload_sha256 }) => ({ file, upload_sha256 })) }, null, 2)) });
  expect(errors).toEqual([]);
});
