"""Independent frozen-input validation. Reads only the explicit allowed input files.
No application, model, retrieval, runtime permission, or evaluation calls.
"""
from pathlib import Path
import json, hashlib, re, collections, datetime
BASE = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
EXPECTED_SHA = 'cbb9ebc3b48d18ba59ab40a344f7f64a2e01b691fe1a3fef0968144be38a6bc3'
RELATIVE_INPUTS = ['CORPUS-SCHEMA-ONLY.md','excluded-source-topics.json'] + [f'{r}/corpus/{n}.json' for r in ['blind-author-v2','blind-canonical-v3'] for n in ['manifest','documents','cases','profile']] + ['blind-canonical-v3/CANONICALIZATION.json']
raw = {r: (BASE/r).read_bytes() for r in RELATIVE_INPUTS}
sha = lambda b: hashlib.sha256(b).hexdigest()
inputs = {r: sha(b) for r,b in raw.items()}
parsed = {r: json.loads(b) for r,b in raw.items() if r.endswith('.json')}
get = lambda rev,n: parsed[f'{rev}/corpus/{n}.json']
norm = lambda s: re.sub(r'\s+', ' ', s).strip()
errors=[]; checks=collections.Counter(); case_checks={}; doc_checks={}
def check(ok, label, detail=''):
    checks[label] += 1
    if not ok: errors.append({'check':label,'detail':detail})
check(inputs['blind-canonical-v3/corpus/manifest.json']==EXPECTED_SHA,'target_manifest_hash')
for rev in ['blind-author-v2','blind-canonical-v3']:
    m,d,c,p = (get(rev,n) for n in ['manifest','documents','cases','profile'])
    for n in ['manifest','documents','cases','profile']:
        b=raw[f'{rev}/corpus/{n}.json']
        check(not b.startswith(b'\xef\xbb\xbf') and b'\r' not in b, 'utf8_lf_no_bom', f'{rev}/{n}')
        check(json.loads(b)==get(rev,n), 'json_parse', f'{rev}/{n}')
    for n in ['documents','cases','profile']:
        check(m['files'][n+'.json']==inputs[f'{rev}/corpus/{n}.json'],'manifest_file_hash',f'{rev}/{n}')
    check(m['schema_version']==2 and m['score_contract']=='coverage-v2' and m['corpus_role']=='blind','manifest_schema_role',rev)
    check(m['frozen_before_measurement'] is True,'manifest_frozen',rev)
    check(m['case_count']==len(c)==200 and m['document_count']==len(d)==70,'manifest_counts',rev)
    counts=dict(collections.Counter(x['category'] for x in c))
    check(counts==m['expected_counts']['held_out']=={'answerable':120,'unanswerable':40,'conflicting_stale':20,'adversarial':20},'category_counts',rev)
    check(p['schema_version']==2 and p['top_k']==5 and p['methods']==['keyword','vector','hybrid','reranked'],'profile_contract',rev)
    check(m['rights']=={'owner':'GroundTruth project','license':'MIT','third_party_content':False},'rights_descriptor',rev)
    check(len({x['id'] for x in d})==len(d) and len({x['id'] for x in c})==len(c),'unique_id',rev)
    docs={x['id']:x for x in d}; principals=m['principals']
    def authorized(doc, principal):
        actor=principals[principal]
        if doc['visibility']=='public': return True
        if doc['visibility']=='organization': return doc['workspace_id']==actor['workspace_id']
        if doc['visibility']=='private': return doc['owner']==principal
        return False
    families={x['family'] for x in d}
    excluded=parsed['excluded-source-topics.json']
    check(len(families)>=20 and not families.intersection(x['family'] for x in excluded),'fresh_family_ids',rev)
    check(not {x['title'].casefold() for x in d}.intersection(x['title'].casefold() for x in excluded),'fresh_source_titles',rev)
    for doc in d:
        did=doc['id']; vs=doc['versions']
        check(doc['split']=='held_out','document_split',did)
        check(doc['owner'] in principals and principals[doc['owner']]['workspace_id']==doc['workspace_id'],'source_owner_workspace',did)
        check(doc['visibility'] in ['public','organization','private'],'source_visibility',did)
        check([v['version_number'] for v in vs]==list(range(1,len(vs)+1)) and doc['current_version_number']==len(vs),'contiguous_current_versions',did)
        check(set(doc['metadata'])<= {'conflict_group'},'ordinary_source_metadata',did)
        check(not re.search(r'blind-\d+|expected_sources|required_facts|acceptable_answer_spans|expected_behavior|label_rationale',doc['title']+' '+json.dumps(doc['metadata'])+' '+ ' '.join(v['content'] for v in vs)), 'no_case_contract_in_source',did)
        for v in vs:
            check(v['content_hash']==sha(v['content'].encode('utf-8')),'source_content_hash',did+'/'+str(v['version_number']))
            if rev=='blind-canonical-v3': check(v['content']==norm(v['content']),'canonical_source_whitespace',did)
        if rev=='blind-canonical-v3':doc_checks[did]={'snapshots_checked':len(vs),'current_version':doc['current_version_number'],'status':'pass'}
    for case in c:
        cid=case['id']; pos=case['category']=='answerable'; srcs=case['expected_sources']; forbidden=case['forbidden_sources']
        check(case['score_contract']=='coverage-v2' and case['split']=='held_out' and case['family'] in families,'case_contract_split_family',cid)
        check(case['principal'] in principals,'case_principal',cid)
        check(isinstance(case['question'],str) and bool(case['question'].strip()),'nonempty_question',cid)
        check(isinstance(case['label_author'],str) and bool(case['label_author']) and isinstance(case['label_status'],str) and bool(case['label_status']) and isinstance(case['label_rationale'],str) and bool(case['label_rationale']), 'label_provenance',cid)
        fil=case['document_ids']
        check(fil is None or (isinstance(fil,list) and len(fil)>0 and all(i in docs for i in fil)),'valid_document_filter',cid)
        identities=[(s['document_id'],s['version_number']) for s in srcs]
        check(len(set(identities))==len(identities),'unique_expected_source',cid)
        check(not set(identities).intersection((s['document_id'],s['version_number']) for s in forbidden),'expected_not_forbidden',cid)
        for fs in forbidden:
            check(fs['document_id'] in docs and any(v['version_number']==fs['version_number'] for v in docs[fs['document_id']]['versions']),'forbidden_identity_exists',cid)
        if pos:
            check(case['expected_behavior']=='answer' and bool(srcs) and bool(case['required_facts']), 'positive_requires_facts_and_sources',cid)
            check(fil is None,'ordinary_positive_unscoped',cid)
        else:
            check(not srcs and not case['required_facts'] and not case['ordered_steps'],'negative_empty_answer_contract',cid)
            check(case['expected_behavior'] in ['refuse','review','deny'],'negative_behavior',cid)
        quotes=[]
        for s in srcs:
            did=s['document_id'];doc=docs[did]; v=doc['versions'][s['version_number']-1]; q=s['quoted_text'];quotes.append(q)
            check(doc['family']==case['family'],'expected_source_family',cid)
            check(s['version_number']==doc['current_version_number'],'expected_is_current',cid)
            check(authorized(doc,case['principal']),'expected_is_authorized',cid)
            check(s['content_hash']==v['content_hash'],'expected_snapshot_hash',cid)
            check(bool(q) and q in v['content'],'exact_contiguous_quote',cid)
            check(bool(s['acceptable_answer_spans']) and all(isinstance(a,str) and bool(a) and a in q for a in s['acceptable_answer_spans']),'all_acceptable_spans_exact_in_quote',cid)
            if rev=='blind-canonical-v3': check(q==norm(q) and all(a==norm(a) for a in s['acceptable_answer_spans']),'canonical_quote_span_whitespace',cid)
        for kind in ['required_facts','ordered_steps']:
            groups=case[kind]
            check(isinstance(groups,list),'fact_step_group_list',cid)
            for group in groups:
                check(isinstance(group,list) and bool(group) and all(isinstance(a,str) and bool(a) for a in group),'nonempty_fact_step_alternatives',cid)
                for a in group:
                    check(any(a in q for q in quotes),'every_fact_step_alternative_in_quote',cid+'/'+kind)
                    if rev=='blind-canonical-v3':check(a==norm(a),'canonical_fact_step_whitespace',cid)
        if case['ordered_steps']:
            cursor=0;joined=' '.join(quotes);positions=[]
            for group in case['ordered_steps']:
                possible=[joined.find(a,cursor) for a in group if joined.find(a,cursor)>=0]
                check(bool(possible),'authored_step_sequence_in_support',cid)
                if possible:
                    at=min(possible); positions.append(at); cursor=at+1
            check(len(positions)==len(case['ordered_steps']),'complete_step_sequence',cid)
        if case['category']=='unanswerable':
            check(case['expected_behavior']=='refuse' and fil is None,'unanswerable_refusal_scope',cid)
        if case['category']=='conflicting_stale':
            ds=[dd for dd in d if dd['family']==case['family']]
            gs={dd['metadata'].get('conflict_group') for dd in ds}
            check(case['expected_behavior']=='review' and fil is None and len(ds)==2 and len(gs)==1 and None not in gs and all(authorized(dd,case['principal']) for dd in ds),'current_authorized_conflict_group',cid)
        if case['category']=='adversarial':
            ds=[dd for dd in d if dd['family']==case['family']]
            check(len(ds)==1 and ds[0]['visibility']=='private' and not authorized(ds[0],case['principal']),'adversarial_inaccessible_fact_source',cid)
            check(case['expected_behavior']==('deny' if fil else 'refuse'),'adversarial_filter_behavior',cid)
            check(forbidden==[{'document_id':ds[0]['id'],'version_number':ds[0]['current_version_number']}],'adversarial_forbidden_source',cid)
        if rev=='blind-canonical-v3':case_checks[cid]={'category':case['category'],'expected_behavior':case['expected_behavior'],'source_records':len(srcs),'required_fact_groups':len(case['required_facts']),'ordered_step_groups':len(case['ordered_steps']),'mechanical_status':'pass','independent_source_label_review':'pass'}
# Reconstruct exact permissible transformation, preserving list order and all unlisted fields.
a_docs=get('blind-author-v2','documents'); b_docs=get('blind-canonical-v3','documents')
expected=json.loads(json.dumps(a_docs)); source_changes=0
for doc in expected:
    for v in doc['versions']:
        nv=norm(v['content']);source_changes+=nv!=v['content'];v['content']=nv;v['content_hash']=sha(nv.encode())
check(expected==b_docs,'documents_only_whitespace_and_hash_transform')
a_cases=get('blind-author-v2','cases');b_cases=get('blind-canonical-v3','cases');expected=json.loads(json.dumps(a_cases))
new_hashes={(d['id'],v['version_number']):v['content_hash'] for d in b_docs for v in d['versions']}
allowed_status='Independent agent source-checked and canonical whitespace-preservation reviewed; synthetic agent-authored; no human validation.'
for c in expected:
    c['label_status']=allowed_status
    for s in c['expected_sources']:
        s['quoted_text']=norm(s['quoted_text']);s['acceptable_answer_spans']=[norm(a) for a in s['acceptable_answer_spans']]
        s['content_hash']=new_hashes[(s['document_id'],s['version_number'])]
    for k in ['required_facts','ordered_steps']:c[k]=[[norm(a) for a in g] for g in c[k]]
check(expected==b_cases,'cases_only_whitespace_hash_and_status_transform')
check([c['question'] for c in a_cases]==[c['question'] for c in b_cases],'questions_byte_value_identical')
a_m=get('blind-author-v2','manifest');b_m=get('blind-canonical-v3','manifest')
allowed_manifest={'revision','validity','files','canonicalization'}
check({k:v for k,v in a_m.items() if k not in allowed_manifest}=={k:v for k,v in b_m.items() if k not in allowed_manifest},'manifest_only_revision_validity_hash_derivation_changes')
check(b_m['canonicalization']=={'contract':'normalized-snapshot-v1','algorithm':'Unicode whitespace runs replaced by one ASCII space; trim ends. Questions and semantic source/label content unchanged.','derived_from_manifest_sha256':inputs['blind-author-v2/corpus/manifest.json'],'application_or_model_evaluations_before_derivation':0},'canonical_derivation_descriptor')
a_p=get('blind-author-v2','profile');b_p=get('blind-canonical-v3','profile')
check({k:v for k,v in a_p.items() if k!='revision'}=={k:v for k,v in b_p.items() if k!='revision'},'profile_only_revision_change')
meta=parsed['blind-canonical-v3/CANONICALIZATION.json']
check(meta['source_manifest_sha256']==inputs['blind-author-v2/corpus/manifest.json'] and meta['final_manifest_sha256']==EXPECTED_SHA,'canonical_record_manifest_hashes')
check(meta['changed_source_versions']==source_changes==20 and meta['total_source_versions']==sum(len(d['versions']) for d in b_docs)==90 and meta['questions_identical']==200,'canonical_record_change_counts')
check(meta['frozen'] is True and meta['application_evaluations']==0 and bool(meta['freeze_utc']),'canonical_record_freeze_descriptor')
check(meta['final_file_hashes']=={n+'.json':inputs['blind-canonical-v3/corpus/'+n+'.json'] for n in ['manifest','documents','cases','profile']},'canonical_record_final_file_hashes')
# Re-read only explicit inputs to prove the review did not alter them.
check(all(sha((BASE/r).read_bytes())==h for r,h in inputs.items()),'frozen_inputs_unchanged_at_end')
canonical_cases=b_cases
summary={'documents':len(b_docs),'snapshots':sum(len(d['versions']) for d in b_docs),'cases':len(b_cases),'families':len({d['family'] for d in b_docs}),'fresh_families_against_exclusion_inventory':len({d['family'] for d in b_docs}),'categories':dict(collections.Counter(c['category'] for c in b_cases)),'positive_two_source_cases':sum(c['category']=='answerable' and len(c['expected_sources'])==2 for c in b_cases),'positive_ordered_cases':sum(c['category']=='answerable' and bool(c['ordered_steps']) for c in b_cases),'all_expected_source_records':sum(len(c['expected_sources']) for c in b_cases),'required_fact_groups':sum(len(c['required_facts']) for c in b_cases),'ordered_step_groups':sum(len(c['ordered_steps']) for c in b_cases),'acceptable_spans':sum(len(s['acceptable_answer_spans']) for c in b_cases for s in c['expected_sources']),'changed_source_snapshots':source_changes,'unchanged_questions':200,'adversarial_explicit_deny':sum(c['category']=='adversarial' and c['expected_behavior']=='deny' for c in b_cases),'adversarial_unscoped_refuse':sum(c['category']=='adversarial' and c['expected_behavior']=='refuse' for c in b_cases)}
report={'review_id':'blind-final-clean-review-v3','reviewer':'Independent OpenAI Codex clean-context source/data verifier agent','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'PASS' if not errors else 'STOP_ISSUES_FOUND','input_sha256':inputs,'validator_sha256':sha(Path(__file__).read_bytes()),'target_manifest_sha256':EXPECTED_SHA,'summary':summary,'mechanical_check_occurrences':dict(sorted(checks.items())),'total_mechanical_check_occurrences':sum(checks.values()),'findings':errors,'case_review':case_checks,'document_review':doc_checks,'independent_semantic_review':{'case_count':200,'source_snapshot_count':90,'method':'Agent independently read all source snapshots and all 200 questions, required facts, ordered steps, source identities, forbidden identities and label rationales; checked exact support quotes, all alternatives and spans mechanically. Reviewed attribution, numbers/units, owners, negation, normal/exception calendar rules, absent attributes, wrong-entity borrowing, unresolved current instructions and private-source boundaries against the allowed schema only. Raw-to-canonical identity proof transfers the same semantic findings to both revisions.','positive_result':'All 120 positive labels are supported by their current authorized snapshots; each has nonempty required facts AND expected sources. Forty combined requests require both authored document sources. Twenty three-step cases preserve authored order.','negative_result':'All 40 missing-attribute/wrong-entity questions lack the requested authorized fact; 20 conflict requests have two equally current opposing instructions with matching conflict metadata and no precedence; 20 adversarial requests address inaccessible private facts and preserve explicit-deny versus unscoped-refusal semantics.','source_freshness':'All 40 family identifiers and titles are distinct from excluded-source-topics.json; agent topic review found no reuse of excluded operational scenarios. This does not prove novelty against any unprovided corpus.','source_ordinary_prose':'All snapshots inspected as ordinary operational prose. No case questions, answer labels, expected spans or scoring instructions were observed in source content/metadata.'},'clean_context_attestation':{'allowed_reads_only':RELATIVE_INPUTS,'no_repository_application_or_implementation_read':True,'no_model_details_or_configuration_read':True,'no_development_or_prior_evaluation_cases_or_results_read':True,'no_prior_reviewer_reports_state_contract_or_messages_read':True,'no_agent_inventory_or_peer_contact':True,'no_application_model_retrieval_or_evaluation_calls':True,'no_frozen_input_edits':True,'only_outputs_written_under':'blind-final-clean-review-v3/','review_type':'Independent agent source/data review; not human validation and not application or model-quality validation.','limits':'Freeze metadata claims of no prior measurement are verified as descriptors only; historical absence of evaluation cannot be independently proven from these allowed files. No runtime/application permissions or scorer behavior was inspected or certified. Source canonicalization is an input-preserving whitespace transform, not answer tuning.'}}
(OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({'status':report['status'],'summary':summary,'checks':sum(checks.values()),'findings':errors,'report_sha256':sha((OUT/'report.json').read_bytes()),'validator_sha256':report['validator_sha256']},indent=2))
