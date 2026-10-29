// C399 live-only actual-browser harness. No routes/fulfills/successful API doubles.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, readFile, readdir, writeFile, access, rename} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const prep = path.dirname(fileURLToPath(import.meta.url));
const q = path.dirname(prep);
const args = process.argv.slice(2);
if (args[0] !== '--execute' || args[1] !== '--run-dir' || args.length !== 3) {
  throw new Error('Live execution requires the fixed coordinator and --execute --run-dir. No seed was read.');
}
const run = path.resolve(args[2]);
assert(path.relative(path.join(prep, 'runs'), run).match(/^[a-z0-9][a-z0-9-]{0,63}$/));
const FRONT = 'http://127.0.0.1:3506';
const API = 'http://127.0.0.1:8401';
const viewportList = [{width:390,height:844},{width:768,height:1024},{width:1440,height:900}];
const markerNames = new Set(['contexts-ready','api-down','retry-failed','api-ready','browser-done','browser-failed']);
const require = createRequire(path.join(q, '../delivery-worktree/apps/web/package.json'));
const {chromium, expect} = require('@playwright/test');
let secrets = [];
let browser;
const states = [];
const exists = async file => {try {await access(file); return true;} catch {return false;}};
const redact = text => secrets.reduce((value, secret) => value.replaceAll(secret, '[redacted]'), String(text));
const save = async (name, value) => {
  assert(/^[a-z0-9-]+\.json$/.test(name));
  const text = JSON.stringify(value, null, 2) + '\n';
  assert(secrets.every(secret => !text.includes(secret)), 'Credential in evidence');
  assert(!text.includes('"api_key"'), 'Private manifest data must not be evidence');
  await writeFile(path.join(run, name), text, {flag:'wx'});
};
const marker = async name => {
  assert(markerNames.has(name));
  const destination=path.join(run,name+'.json');
  assert(!await exists(destination));
  const temporary=path.join(run,name+'.pending');
  await writeFile(temporary,JSON.stringify({phase:name,viewports:[390,768,1440]})+'\n',{flag:'wx'});
  await rename(temporary,destination);
};
const waitMarker = async name => {
  assert(markerNames.has(name));
  const deadline = Date.now() + 360000;
  while (!await exists(path.join(run, name + '.json'))) {
    if (await exists(path.join(run, 'coordinator-abort.json'))) throw new Error('Coordinator requested safe browser cleanup');
    assert(Date.now() < deadline, 'IPC deadline exceeded');
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  assert.deepEqual(JSON.parse(await readFile(path.join(run,name+'.json'),'utf8')), {phase:name,viewports:[390,768,1440]});
};
const get = async (route, key, expected=200) => {
  assert(route.startsWith('/api/'));
  const response = await fetch(API + route, {headers:{'X-API-Key':key}});
  assert.equal(response.status, expected, 'Actual authorized HTTP status');
  return response.json();
};
const basePaths = ['/api/identity','/api/documents','/api/queries','/api/conversations','/api/health'];
// Capture each completed JSON body before unrelated route/identity transitions.
// Exact request-key matching rejects a preceding provider generation; headers
// and keys are never retained in observation DTOs or logs.
const providerWaits = (page, key) => basePaths.map(endpoint => page.waitForResponse(response => new URL(response.url()).origin === API && new URL(response.url()).pathname === endpoint && response.request().method() === 'GET' && response.request().headers()['x-api-key'] === key).then(async response => ({status:response.status(), body:await response.json()})));
const assertProviderResponses = async promises => {
  const responses = await Promise.all(promises);
  for (const response of responses) assert.equal(response.status, 200, 'Provider must finish real authorized reads');
  return responses;
};
const readyUI = async state => {
  await expect(state.page.getByText('Connected local application',{exact:true})).toBeVisible();
  await expect(state.page.locator('.gt-source-bar')).toContainText(state.alias);
  await expect(state.page.locator('.gt-source-bar')).toContainText(state.workspace);
  await expect(state.page.locator('main')).not.toContainText(/Loading saved investigations|Loading durable usage and audit history|Loading recorded events/);
};
const screenshot = async (state, label) => {
  assert(/^[a-z0-9-]+$/.test(label));
  await expect(state.page.getByLabel('API key',{exact:true})).toHaveCount(0);
  assert(secrets.every(secret => !state.page.url().includes(secret)));
  assert(await state.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal page clipping');
  assert(await state.page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches));
  await expect(state.page.locator('nextjs-portal,vite-error-overlay,#webpack-dev-server-client-overlay')).toHaveCount(0);
  await state.page.screenshot({path:path.join(run,'screenshots',`${label}-${state.viewport.width}.png`),fullPage:false});
};
const connect = async (state, principal, alias) => {
  state.phase = 'identity-connect';
  await state.page.getByRole('button',{name:'Connection',exact:true}).click();
  await expect(state.page.getByRole('dialog')).toContainText('API: ' + API);
  await state.page.getByLabel('API key',{exact:true}).evaluate((element,value)=>{
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(element,value);
    element.dispatchEvent(new Event('input',{bubbles:true}));
  },principal.api_key);
  const waits = providerWaits(state.page, principal.api_key);
  await state.page.getByRole('button',{name:'Connect application',exact:true}).click();
  const responses = await assertProviderResponses(waits);
  const identity = responses[0].body;
  assert.equal(identity.is_admin,false,'Each cohort must be a non-admin private owner');
  assert.equal(identity.workspace_id,principal.workspace_id);
  state.alias=alias; state.workspace=principal.workspace_id; state.key=principal.api_key;
  await readyUI(state);
  return responses;
};
const assertAnswer = async (state, record) => {
  assert.equal(record.outcome,'completed');
  const answer = state.page.getByLabel('Answer and evidence');
  await expect(answer.locator('.gt-answer-text')).toHaveText(record.answer,{timeout:45000});
  await expect(answer.getByLabel('Answer selection evidence')).toContainText('Exact instruction coverage verified');
  await expect(answer.getByLabel('Answer selection evidence')).toContainText('Recorded output hash: matched');
  assert.equal(new URL(state.page.url()).searchParams.get('query'),record.id);
  assert(await state.page.evaluate(key=>sessionStorage.getItem('groundtruth.api-key.v1')===key,state.key),'Session key retained without logging it');
};
const navigateSaved = async state => {
  state.phase='navigation';
  const waits=providerWaits(state.page, state.key);
  const saved=state.page.waitForResponse(response=>new URL(response.url()).origin===API && new URL(response.url()).pathname===`/api/queries/${state.record.id}`);
  await state.page.goto(`${FRONT}/chat?query=${encodeURIComponent(state.record.id)}`);
  await assertProviderResponses(waits); assert.equal((await saved).status(),200);
  await readyUI(state); await assertAnswer(state,state.record);
};

try {
  const seedPath=process.env.GROUNDTRUTH_SEED_MANIFEST;
  assert(seedPath && path.resolve(seedPath)===path.resolve(q,'typed-connected-live-v378/private/seed.json'));
  // This is the only seed read and occurs solely in authorized live execution.
  let seed;
  try{seed=JSON.parse(await readFile(seedPath,'utf8'));}catch{throw new Error('Private seed JSON could not be read; contents omitted');}
  secrets=Object.values(seed.principals||{}).map(principal=>principal.api_key).filter(value=>typeof value==='string' && value.length>15);
  assert(seed.api_url===API,'Private seed API target mismatch'); assert(seed.seed_status==='complete','Private seed is incomplete');
  assert.equal(new Set(secrets).size,secrets.length);
  const cohorts=viewportList.map(viewport=>seed.typed_connected_v360.projects[String(viewport.width)]);
  assert.equal(new Set(cohorts.map(project=>project.principal_alias)).size,3);
  assert.equal(new Set(cohorts.map(project=>seed.principals[project.principal_alias].workspace_id)).size,3);
  assert.equal(new Set(cohorts.flatMap(project=>Object.values(project.documents).map(document=>document.document_id))).size,9);
  await mkdir(path.join(run,'screenshots'));
  const historyRoot=path.join(q,'typed-connected-visual-v388/records-before-restart');
  const historyFiles=await readdir(historyRoot);
  browser=await chromium.launch({headless:true}); // No recording/tracing/video.
  for (const viewport of viewportList) {
    const project=seed.typed_connected_v360.projects[String(viewport.width)];
    const principal=seed.principals[project.principal_alias];
    const procedureID=project.documents['typed-lumen-procedure'].document_id;
    const anchors=[];
    for (const name of historyFiles.filter(name=>new RegExp(`^${viewport.width}-[0-9a-f-]{36}\\.json$`,'i').test(name))) {
      const record=JSON.parse(await readFile(path.join(historyRoot,name),'utf8'));
      if (record.outcome==='completed' && record.sources.some(source=>source.document_id===procedureID && source.document_version===2)) anchors.push(record);
    }
    assert.equal(anchors.length,1,'Select the known v388 current-v2 record, not a fixed history count');
    const current=await get(`/api/queries/${encodeURIComponent(anchors[0].id)}`,principal.api_key);
    assert.equal(current.answer,anchors[0].answer); assert.deepEqual(current.sources,anchors[0].sources);
    const listing=await get('/api/queries?limit=100',principal.api_key);
    assert(listing.queries.some(item=>item.id===current.id)); // C400 may add more entries.
    const context=await browser.newContext({viewport,reducedMotion:'reduce'});
    const page=await context.newPage();
    const state={context,page,viewport,phase:'initial',project,key:principal.api_key,alias:project.principal_alias,workspace:principal.workspace_id,record:current,issues:[],apiFailures:[],apiResponses:[],requests:[]};
    states.push(state);
    page.on('pageerror',error=>state.issues.push({type:'pageerror',phase:state.phase,text:redact(error.message),expected:false}));
    page.on('console',message=>{
      if(message.type()!=='error')return;
      const text=redact(message.text());
      let location;try{location=new URL(message.location().url);}catch{location=null;}
      const transport=location?.origin===API && ['outage','retry-down'].includes(state.phase) && /ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET|Failed to fetch|Failed to load resource|NetworkError/.test(text);
      const denied=location?.origin===API && ((state.phase==='admin' && location.pathname.startsWith('/api/v1/admin/') && /403/.test(text)) || (state.phase==='identity-denied' && location.pathname===`/api/queries/${state.record.id}` && /404/.test(text)));
      state.issues.push({type:'console',phase:state.phase,text,expected:transport||denied});
    });
    page.on('request',request=>{
      const url=new URL(request.url());
      state.requests.push({phase:state.phase,origin:url.origin,path:url.pathname,method:request.method()});
      if(![FRONT,API].includes(url.origin)||secrets.some(secret=>request.url().includes(secret)))state.issues.push({type:'request',phase:state.phase,text:'Unexpected origin or credential URL',expected:false});
    });
    page.on('requestfailed',request=>{
      const url=new URL(request.url()); const failure=request.failure()?.errorText||'unknown';
      const expected=url.origin===API && ['outage','retry-down'].includes(state.phase) && /ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET|ERR_FAILED/.test(failure);
      const canceled=/ERR_ABORTED/.test(failure)&&[FRONT,API].includes(url.origin)&&['navigation','admin','identity-connect','identity-denied','sample','recovery'].includes(state.phase);
      state.apiFailures.push({phase:state.phase,path:url.pathname,error:redact(failure),expected:expected||canceled});
    });
    page.on('response',response=>{const url=new URL(response.url());if(url.origin===API)state.apiResponses.push({phase:state.phase,path:url.pathname,status:response.status(),method:response.request().method()});});
    await page.goto(FRONT+'/chat');
    await connect(state,principal,project.principal_alias);
    await navigateSaved(state);
    await save(`baseline-${viewport.width}.json`,{qualification:'Existing synthetic engineering record, no quality scoring',record:current,history_count_observed:listing.queries.length});
  }
  await marker('contexts-ready');
  await waitMarker('api-down');
  for(const state of states){
    state.phase='outage';
    await state.page.reload({waitUntil:'domcontentloaded'});
    const alerts=state.page.locator('.gt-notice.error[role="alert"]');
    await expect(alerts).toHaveCount(2,{timeout:45000}); // Provider + local saved-read notice.
    await expect(alerts.last()).toContainText('Results have not been replaced with sample data.');
    await expect(state.page.getByText('Connected local application',{exact:true})).toBeVisible();
    await expect(state.page.getByText('Interactive sample data',{exact:true})).toHaveCount(0);
    await expect(state.page.getByLabel('Answer and evidence').locator('.gt-answer-text')).toHaveCount(0);
    assert(state.apiFailures.some(item=>item.phase==='outage'&&item.path===`/api/queries/${state.record.id}`));
    await screenshot(state,'outage');
    state.phase='retry-down';
    const attempted=state.page.waitForRequest(request=>new URL(request.url()).origin===API && new URL(request.url()).pathname===`/api/queries/${state.record.id}` && request.method()==='GET');
    const failed=state.page.waitForEvent('requestfailed',{predicate:request=>new URL(request.url()).origin===API && new URL(request.url()).pathname===`/api/queries/${state.record.id}` && request.method()==='GET'});
    // Source order is provider notice then local saved-read notice. Matching an
    // actual saved GET proves the selected Retry is local, not provider refresh.
    await alerts.last().getByRole('button',{name:'Retry',exact:true}).click();
    await attempted;
    assert(/ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET|ERR_FAILED/.test((await failed).failure()?.errorText||''),'Retry must encounter an actual transport failure while API is down');
    await expect(alerts).toHaveCount(2,{timeout:45000});
    assert(new URL(state.page.url()).searchParams.get('query')===state.record.id);
    await screenshot(state,'retry-still-down');
  }
  await marker('retry-failed');
  await waitMarker('api-ready');
  for(const state of states){
    state.phase='recovery';
    const alerts=state.page.locator('.gt-notice.error[role="alert"]');
    const documentEpoch=await state.page.evaluate(()=>performance.timeOrigin);
    const saved=state.page.waitForResponse(response=>new URL(response.url()).origin===API && new URL(response.url()).pathname===`/api/queries/${state.record.id}` && response.request().method()==='GET');
    const postsBefore=state.requests.filter(item=>item.method==='POST'&&item.origin===API).length;
    await alerts.last().getByRole('button',{name:'Retry',exact:true}).click();
    const recovered=await saved; assert.equal(recovered.status(),200);
    const dto=await recovered.json(); assert.equal(dto.answer,state.record.answer); assert.deepEqual(dto.sources,state.record.sources);
    await assertAnswer(state,state.record);
    assert.equal(await state.page.evaluate(()=>performance.timeOrigin),documentEpoch,'Local Retry recovers without reload/navigation');
    assert.equal(state.requests.filter(item=>item.method==='POST'&&item.origin===API).length,postsBefore,'Retry must not resubmit a query POST');
    await expect(alerts).toHaveCount(1); // Remaining provider notice is distinct.
    await screenshot(state,'local-retry-recovered');
    const waits=providerWaits(state.page, state.key);
    await alerts.first().getByRole('button',{name:'Retry',exact:true}).click();
    await assertProviderResponses(waits); await readyUI(state); await expect(alerts).toHaveCount(0);
    await state.page.reload(); // Separate session/persistence check after Retry proof.
    await readyUI(state); await assertAnswer(state,state.record);
    const citation=state.page.getByLabel('Answer and evidence').locator('.gt-source-card').first();
    await citation.focus(); await state.page.keyboard.press('Enter');
    await expect(state.page.getByRole('dialog').getByLabel('Canonical quoted evidence')).toHaveText(state.record.sources[0].quoted_text);
    await screenshot(state,'recovered-source');
    await state.page.keyboard.press('Escape'); await expect(citation).toBeFocused();
    await save(`recovered-${state.viewport.width}.json`,{actual_saved_get:dto,local_retry_without_reload:true,retry_query_post_count:0,session_key_retained:true});
  }
  // Stable six-route captures after recovery, including final non-admin state.
  for(const state of states){
    for(const route of ['/','/chat','/documents','/workflows','/workflow','/admin']){
      state.phase=route==='/admin'?'admin':'navigation';
      const waits=providerWaits(state.page, state.key);
      const extra=route==='/workflows'?state.page.waitForResponse(response=>new URL(response.url()).origin===API&&new URL(response.url()).pathname==='/api/v1/workflows/definitions'):null;
      const admin=route==='/admin'?['/api/v1/admin/usage','/api/v1/admin/audit'].map(endpoint=>state.page.waitForResponse(response=>new URL(response.url()).origin===API&&new URL(response.url()).pathname===endpoint)):[];
      await state.page.goto(FRONT+(route==='/chat'?`/chat?query=${encodeURIComponent(state.record.id)}`:route));
      const responses=await assertProviderResponses(waits); await readyUI(state);
      assert.equal((responses[0].body).is_admin,false);
      await expect(state.page.getByRole('heading',{level:1}).first()).toBeVisible();
      if(route==='/chat')await assertAnswer(state,state.record);
      if(route==='/documents')await expect(state.page.getByRole('article')).toHaveCount(3);
      if(extra){const definitions=await extra;assert.equal(definitions.status(),200);const observed=await definitions.json();assert(Array.isArray(observed));await expect(state.page.getByRole('combobox',{name:'Workflow definition',exact:true}).locator('option')).toHaveCount(observed.length+1);await expect(state.page.getByRole('combobox',{name:'Document',exact:true}).locator('option')).toHaveCount(4);}
      if(route==='/admin'){
        for(const response of await Promise.all(admin))assert.equal(response.status(),403);
        await expect(state.page.getByText('Administrator access is required.',{exact:false})).toBeVisible();
        await expect(state.page.getByText('Loading durable usage and audit history…',{exact:true})).toHaveCount(0);
        await expect(state.page.getByText('Loading recorded events…',{exact:true})).toHaveCount(0);
        await expect(state.page.getByText('No audit data was substituted after this error.',{exact:true})).toBeVisible();
        await expect(state.page.getByLabel('Recorded audit events')).toHaveCount(0);
      }else await expect(state.page.locator('.gt-notice.error[role="alert"]')).toHaveCount(0);
      await state.page.evaluate(()=>window.scrollTo(0,0));
      await screenshot(state,'route-'+(route==='/'?'overview':route.slice(1)));
    }
  }
  for(let index=0;index<states.length;index++){
    const state=states[index];
    await navigateSaved(state);
    state.phase='sample';
    const firstAPI=state.requests.length;
    await state.page.locator('.gt-source-bar').getByRole('button',{name:'Explore sample data',exact:true}).click();
    await expect(state.page.getByText('Interactive sample data',{exact:true})).toBeVisible();
    assert.equal(new URL(state.page.url()).searchParams.get('query'),null);
    await expect(state.page.locator('body')).not.toContainText('Place two tokens');
    await expect(state.page.locator('.gt-source-bar')).not.toContainText(state.workspace);
    await state.page.goto(FRONT+'/documents');
    await expect(state.page.getByText('Interactive sample data',{exact:true})).toBeVisible();
    assert.equal(state.requests.slice(firstAPI).filter(item=>item.origin===API).length,0,'Explicit sample must not request private API data');
    const sampleText=await state.page.locator('main').innerText();
    assert(!Object.values(state.project.documents).some(document=>sampleText.includes(document.document_id)));
    await screenshot(state,'explicit-sample');
    const other=states[(index+1)%states.length];
    const principal=seed.principals[other.project.principal_alias];
    const responses=await connect(state,principal,other.project.principal_alias);
    const docs=responses[1].body;
    assert.deepEqual(docs.documents.map(document=>document.id).sort(),Object.values(other.project.documents).map(document=>document.document_id).sort());
    assert.equal(new URL(state.page.url()).searchParams.get('query'),null);
    const foreign=state.page.waitForResponse(response=>new URL(response.url()).origin===API&&new URL(response.url()).pathname===`/api/queries/${state.record.id}`);
    state.phase='identity-denied';
    await state.page.goto(`${FRONT}/chat?query=${encodeURIComponent(state.record.id)}`);
    assert.equal((await foreign).status(),404,'Other private owner must not read prior owner history');
    await expect(state.page.locator('.gt-notice.error[role="alert"]').last()).toBeVisible();
    await expect(state.page.getByLabel('Answer and evidence').locator('.gt-answer-text')).toHaveCount(0);
    await expect(state.page.getByLabel('Answer and evidence').locator('.gt-source-card')).toHaveCount(0);
    await screenshot(state,'identity-denied');
    await connect(state,seed.principals[state.project.principal_alias],state.project.principal_alias);
    await navigateSaved(state);
    assert.equal(state.issues.filter(issue=>!issue.expected).length,0,'Unexpected console/page/navigation failure');
    assert.equal(state.apiFailures.filter(issue=>!issue.expected).length,0,'Unexpected request failure');
    await save(`browser-observation-${state.viewport.width}.json`,{viewport:state.viewport,known_query_id:state.record.id,stable_routes:6,local_retry_no_reload:true,explicit_sample_private_render_cache_cleared:true,
      session_key_retention:'intentional existing application behavior; no key value recorded',identity_scope_denied:true,issues:state.issues,request_failures:state.apiFailures,api_responses:state.apiResponses});
  }
  for(const name of ['frontend.log','api-restarted.log','browser.log']){
    const text=await readFile(path.join(run,name),'utf8');
    assert(secrets.every(secret=>!text.includes(secret)),'Credential must not appear in execution logs');
  }
  await marker('browser-done');
  console.log(JSON.stringify({viewports:3,stable_routes_per_viewport:6,local_retry_without_reload:true,explicit_sample:true,identity_scope:true,scope:'Actual engineering browser observations only; not model quality'}));
}catch(error){
  await save('browser-error.json',{phase:'failed',message:redact(error?.message||error),stack:redact(error?.stack||''),contexts:states.map(state=>({viewport:state.viewport,phase:state.phase,url:state.page.url(),issues:state.issues,apiFailures:state.apiFailures,apiResponses:state.apiResponses,requests:state.requests}))}).catch(()=>{});
  await marker('browser-failed').catch(()=>{});
  console.error(redact(error?.message||error));
  process.exitCode=1;
}finally{
  for(const state of states)await state.context.close().catch(()=>{});
  if(browser)await browser.close();
}
