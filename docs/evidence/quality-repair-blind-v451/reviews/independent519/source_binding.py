"""Read exact frozen-source paths from Git objects; never checks out or edits."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
HERE=Path(__file__).resolve().parent;Q=HERE.parent;W=Q.parent/'delivery-worktree'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
hashbytes=lambda b:hashlib.sha256(b).hexdigest()
freeze=read(Q/'candidate-freeze-v446/freeze.json');results={}
for name,commit,files in [('candidate',freeze['candidate_commit'],read(Q/'requirements-source-v31.json')['files']),('baseline',freeze['baseline_commit'],read(Q/'baseline-freeze-v417/source-manifest.json')['extracted_runtime_subset'])]:
 argv=['git','-C',str(W),'cat-file','--batch'];request=''.join(commit+':'+p+'\n' for p in files).encode()
 completed=subprocess.run(argv,input=request,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
 assert completed.returncode==0
 output=completed.stdout;offset=0;mismatches=[];newline_only=[];semantic_mismatches=[]
 for path,pin in files.items():
  end=output.index(b'\n',offset);header=output[offset:end].split();assert len(header)==3 and header[1]==b'blob',(path,header)
  length=int(header[2]);body=output[end+1:end+1+length];offset=end+2+length
  if hashbytes(body)!=pin:
   mismatches.append(path)
   snapshot=(Q/('requirements-source-v31' if name=='candidate' else 'baseline-freeze-v417/source')/path).read_bytes()
   if body.replace(b'\r\n',b'\n')==snapshot.replace(b'\r\n',b'\n'):newline_only.append(path)
   else:semantic_mismatches.append(path)
 assert offset==len(output)
 results[name]={'commit':commit,'exact_paths':len(files),'git_exit':completed.returncode,'raw_mismatch_count':len(mismatches),'newline_only_mismatch_count':len(newline_only),'semantic_mismatches':semantic_mismatches,'all_bytes_match':not mismatches,'all_equal_modulo_CRLF':not semantic_mismatches,'command':argv,'stdin_contract':'one commit:path per exact frozen manifest entry; no other tree scan'}
with (HERE/'git-source-normalized-binding.json').open('x',encoding='utf-8') as f:json.dump(results,f,indent=2);f.write('\n')
print(json.dumps(results,indent=2));raise SystemExit(int(any(x['semantic_mismatches'] for x in results.values())))
