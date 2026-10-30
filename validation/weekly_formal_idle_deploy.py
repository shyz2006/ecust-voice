import pathlib,subprocess,time,json,re,fcntl
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/weekly-formal-20261030-r1')
lock=open(stage/'idle-deployment.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
limit=time.monotonic()+3600
while time.monotonic()<limit:
 m=json.loads((stage/'release-manifest.json').read_text())
 if m['activated']:print(json.dumps({'activated':True}),flush=True);break
 result=subprocess.run(['python3',str(stage/'activate.py')],capture_output=True,timeout=900)
 if result.returncode==0:
  print(result.stdout.decode(),flush=True);break
 errors=result.stderr.decode(errors='replace');reason=re.search(r'AssertionError: ([^\n]+)',errors)
 message=reason.group(1) if reason else 'Deployment check failed; see activate-watch-error.log'
 if any(s in message for s in ('Active research:','Active weekly:','Active collection:','Active enrichment:','Active final report:')):
  print(json.dumps({'waiting':message}),flush=True);time.sleep(30);continue
 (stage/'activate-watch-error.log').write_bytes(result.stderr);print(json.dumps({'failed':message}),flush=True);break
else:print(json.dumps({'failed':'No idle deployment window within one hour'}),flush=True)
