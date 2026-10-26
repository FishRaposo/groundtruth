// Read-only HTTP/browser evidence over the public engineering examples.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const q = path.dirname(here);
const w = path.resolve(q, '../delivery-worktree');
const require = createRequire(path.join(w, 'apps/web/package.json'));
const { chromium, expect } = require('@playwright/test');
const seed = JSON.parse(await readFile(path.join(q, 'live-combined-v297/data/seed-manifest.json'), 'utf8'));
const api = new URL(seed.api_url);
assert.equal(api.origin, 'http://127.0.0.1:8402');
const key = seed.principals['admin-a'].api_key;
const secrets = Object.values(seed.principals).map(p => p.api_key).filter(Boolean);
const headers = { 'X-API-Key': key };
const get = async route => {
  const response = await fetch(`${api.origin}/api${route}`, { headers });
  assert.equal(response.status, 200, `Actual API GET failed: ${route}`);
  return response.json();
};
const save = async (name, value) => {
  const text = JSON.stringify(value, null, 2) + '\n';
  for (const secret of secrets) assert(!text.includes(secret), 'Credential excluded from evidence');
  await writeFile(path.join(here, name), text, { flag: 'wx' });
};
await mkdir(path.join(here, 'records-before-restart'));
await mkdir(path.join(here, 'screenshots'));
const listed = (await get('/queries?limit=100')).queries.filter(item => /Cedar|Juniper/.test(item.question));
assert.equal(listed.length, 12);
const records = [];
for (const item of listed) {
  const record = await get(`/queries/${item.id}`);
  if (record.outcome === 'completed') {
    assert.equal(record.provenance.answer_selection.presentation_verification.status, 'verified');
    for (const source of record.sources) {
      const snapshot = await get(`/queries/${record.id}/sources/${source.citation_index}`);
      assert.equal(snapshot.passage, source.quoted_text);
      assert.equal(snapshot.content_hash, source.content_hash);
      assert.equal(snapshot.document_version, source.document_version);
      await save(`records-before-restart/${record.id}-source-${source.citation_index}.json`, snapshot);
    }
  } else {
    assert.equal(record.outcome, 'refused');
    assert.equal(record.answer, null);
    assert.deepEqual(record.sources, []);
  }
  await save(`records-before-restart/${record.id}.json`, record);
  records.push(record);
}
assert.equal(records.filter(item => item.outcome === 'completed').length, 9);
assert.equal(records.filter(item => item.outcome === 'refused').length, 3);
await save('health-before-restart.json', await get('/health'));
const cedar = records.find(item => item.outcome === 'completed' && item.question.includes('Cedar'));
const historical = records.find(item => item.outcome === 'completed' && item.question.includes('Juniper') && item.sources.some(source => source.source_status === 'superseded'));
assert(cedar && historical);
const observations = [];
const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of [{width:390,height:844},{width:768,height:1024},{width:1440,height:900}]) {
    const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('request', request => {
      const origin = new URL(request.url()).origin;
      if (!['http://127.0.0.1:3506', api.origin].includes(origin)) errors.push(`Unexpected network origin: ${origin}`);
    });
    await page.addInitScript(() => {
      if (!sessionStorage.getItem('groundtruth.visual.initialized')) {
        localStorage.setItem('groundtruth.source.v1', 'sample');
        sessionStorage.setItem('groundtruth.visual.initialized', '1');
      }
    });
    await page.goto('http://127.0.0.1:3506/chat');
    await page.getByRole('button', {name:'Connection',exact:true}).click();
    await page.getByLabel('API key', {exact:true}).evaluate((element,value) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(element,value);
      element.dispatchEvent(new Event('input',{bubbles:true}));
    },key);
    await page.getByRole('button',{name:'Connect application',exact:true}).click();
    await expect(page.getByText('Connected local application',{exact:true})).toBeVisible();
    for (const [label, record] of [['numbered',cedar],['historical-paragraphs',historical]]) {
      await page.goto(`http://127.0.0.1:3506/chat?query=${record.id}`);
      const answer = page.getByLabel('Answer and evidence');
      const heading = answer.getByRole('heading',{name:'Source-declared procedure copy',exact:true});
      await expect(heading).toBeVisible({timeout:30000});
      await expect(answer).toContainText('Exact instruction coverage verified');
      await heading.evaluate(element => element.scrollIntoView({block:'start'}));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({path:path.join(here,'screenshots',`proof-${label}-${viewport.width}.png`)});
      if (label === 'historical-paragraphs') {
        const citation = answer.locator('.gt-source-card').first();
        await citation.focus();
        await page.keyboard.press('Enter');
        const dialog = page.getByRole('dialog');
        await expect(dialog).toContainText('superseded');
        await dialog.evaluate(element => element.scrollTo({top:0}));
        await page.screenshot({path:path.join(here,'screenshots',`historical-source-${viewport.width}.png`)});
        await page.keyboard.press('Escape');
        await expect(citation).toBeFocused();
      }
      assert(!page.url().includes(key));
    }
    assert.deepEqual(errors, []);
    observations.push({viewport, keyboard_source_open_close_focus:true, errors, requests:'Only actual frontend/API origins; no successful mocks'});
    await context.close();
  }
} finally {
  await browser.close();
}
await save('result.json',{scope:'Synthetic engineering workflow only; no DEV/blind/model-quality acceptance', completed:9,refused:3,observations});
console.log(JSON.stringify({completed:9,refused:3,viewports:3,screenshots:9,console_errors:0}));
