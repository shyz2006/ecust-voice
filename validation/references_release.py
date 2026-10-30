"""Prepare an immutable candidate and activate with source/image/data guards."""
import base64,hashlib,io,json,pathlib,subprocess,sys,tarfile
repo=pathlib.Path(__file__).resolve().parent.parent
name='references-20261030-r1'
paths=['CampusPulse/report_rendering.py', 'CampusPulse/research.py', 'CampusPulse/weekly.py', 'tests/test_report_repairs.py', 'CampusPulse/report_references.py', 'tests/test_report_references.py']
ssh=[r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@3.17.59.150','sudo -n python3 -']
mode=sys.argv[1] if len(sys.argv)>1 else 'prepare'
if mode=='prepare':
 previous={}
 host_before={x['path']:x['host_sha256'] for x in json.loads((repo/'validation/references-baseline.json').read_text())['files']}
 previous.update({x['path']:x['candidate_sha256'] for x in json.loads((repo/'validation/references-baseline.json').read_text())['files']})
 items=[];payload=io.BytesIO()
 with tarfile.open(fileobj=payload,mode='w:gz') as archive:
  for p in paths:
   old=subprocess.run(['git','show','abe9f1b:production/'+p],cwd=repo,capture_output=True)
   items.append({'path':p,'candidate_sha256':hashlib.sha256((repo/'production'/p).read_bytes()).hexdigest() if (repo/'production'/p).is_file() else None,
                 'expected_before':hashlib.sha256(old.stdout.replace(b'\r\n',b'\n')).hexdigest() if old.returncode==0 else None})
   items[-1]['host_expected']=host_before.get(p)
   items[-1]['expected_before']=previous.get(p,items[-1]['expected_before'])
   if (repo/'production'/p).is_file():archive.add(repo/'production'/p,arcname=p)
  archive.add(repo/'production/tests',arcname='tests',filter=lambda info: None if '__pycache__' in info.name else info)
  archive.add(repo/'host-deployment/Dockerfile.local',arcname='Dockerfile.local')
 script=r'''
import pathlib,subprocess,json,hashlib,tarfile,io,base64,shlex
root=pathlib.Path('/home/ubuntu/bettafish');stage=root/'deploy/NAME';items=ITEMS
def docker(*args):return subprocess.check_output(['sudo','-n','docker',*args])
current=docker('inspect','bettafish','--format','{{.Image}}').decode().strip()
if (stage/'release-manifest.json').exists():
 old=json.loads((stage/'release-manifest.json').read_text());assert not old['activated'] and old['base_image_id']==current,'Release already active or base changed'
blobs={}
for item in items:
 p=item['path'];live=subprocess.run(['sudo','-n','docker','exec','bettafish','cat','/app/'+p],capture_output=True)
 assert (live.returncode==0)==(item['expected_before'] is not None),'Unexpected baseline file: '+p
 item['before_sha256']=hashlib.sha256(live.stdout).hexdigest() if live.returncode==0 else None
 assert item['before_sha256']==item['expected_before'] or (hashlib.sha256(live.stdout.replace(b'\r\n',b'\n')).hexdigest() if live.returncode==0 else None)==item['expected_before'],'Running source changed: '+p
 blobs[p]=live.stdout if live.returncode==0 else None
 host=root/p;item['host_existed']=host.exists() and not p.startswith('tests/')
 if item['host_existed']:
  assert hashlib.sha256(host.read_bytes()).hexdigest()==item['host_expected'],'Host drift: '+p
  backup=stage/'host-backup'/p;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(host.read_bytes())
stage.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(PAYLOAD)),mode='r:gz') as a:a.extractall(stage/'files',filter='data')
for p,data in blobs.items():
 if data is not None:
  backup=stage/'backup'/p;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(data)
if (root/'Dockerfile.local').exists():(stage/'Dockerfile.local.before').write_bytes((root/'Dockerfile.local').read_bytes())
base='bettafish:base-NAME';candidate='bettafish:candidate-NAME';docker('tag',current,base)
build_base=base
config=json.loads(docker('image','inspect',current))[0]['Config']
if len(json.loads(docker('image','inspect',current))[0]['RootFS']['Layers'])>480:
 # Compact the existing filesystem; volumes and database stay outside this image.
 build_base='bettafish:flat-NAME'
 flat_exists=subprocess.run(['sudo','-n','docker','image','inspect',build_base],capture_output=True).returncode==0
 if not flat_exists:
  export_path=stage/'base-rootfs.tar'
  docker('export','-o',str(export_path),'bettafish')
  changes=[]
  for entry in config.get('Env') or []:
   key,value=entry.split('=',1);changes+=['--change','ENV '+key+'='+json.dumps(value,ensure_ascii=False)]
  for key,instruction in [('Cmd','CMD'),('Entrypoint','ENTRYPOINT')]:
   if config.get(key) is not None:changes+=['--change',instruction+' '+json.dumps(config[key])]
  if config.get('WorkingDir'):changes+=['--change','WORKDIR '+config['WorkingDir']]
  if config.get('User'):changes+=['--change','USER '+config['User']]
  for port in config.get('ExposedPorts') or {}:changes+=['--change','EXPOSE '+port]
  for key,value in (config.get('Labels') or {}).items():changes+=['--change','LABEL '+key+'='+json.dumps(value,ensure_ascii=False)]
  docker('import',*changes,str(export_path),build_base)
  # The temporary export is fully recoverable from the tagged running image.
  assert export_path.resolve().is_relative_to(stage.resolve());export_path.unlink()
 compact=json.loads(docker('image','inspect',build_base))[0]['Config']
 for key in ('Env','Cmd','Entrypoint','WorkingDir','User','ExposedPorts'):
  assert (compact.get(key) or None)==(config.get(key) or None),'Image metadata drift: '+key
labels=''.join('LABEL '+key+'='+json.dumps(value,ensure_ascii=False)+'\n' for key,value in (config.get('Labels') or {}).items())
shell='SHELL '+json.dumps(config['Shell'])+'\n' if config.get('Shell') else ''
deleted=['/app/'+i['path'] for i in items if i['candidate_sha256'] is None]
assert all(pathlib.Path(p).is_relative_to('/app') for p in deleted)
remove='RUN python -c '+shlex.quote('from pathlib import Path; [Path(p).unlink(missing_ok=True) for p in '+repr(deleted)+']')+'\n' if deleted else ''
(stage/'Dockerfile').write_text('FROM '+build_base+'\n'+shell+labels+'WORKDIR /app\nCOPY ["files/", "/app/"]\n'+remove)
build=subprocess.run(['sudo','-n','docker','build','--pull=false','-t',candidate,str(stage)],capture_output=True)
assert build.returncode==0,build.stderr.decode(errors='replace')[-500:]
candidate_config=json.loads(docker('image','inspect',candidate))[0]['Config']
for key in ('Env','Cmd','Entrypoint','WorkingDir','User','ExposedPorts','Labels','Shell'):
 assert (candidate_config.get(key) or None)==(config.get(key) or None),'Candidate metadata drift: '+key
for i in items:
 result=subprocess.run(['sudo','-n','docker','run','--rm','--network','none','--entrypoint','cat',candidate,'/app/'+i['path']],capture_output=True)
 assert (hashlib.sha256(result.stdout).hexdigest() if result.returncode==0 else None)==i['candidate_sha256'],i['path']
companions={}
for service in ('collection-api','collection-worker'):
 item=json.loads(docker('inspect','bettafish-'+service))[0]
 tag='bettafish:base-NAME-'+service
 try:docker('tag',item['Image'],tag)
 except subprocess.CalledProcessError:
  exists=subprocess.run(['sudo','-n','docker','image','inspect',tag],capture_output=True).returncode==0
  if not exists:
   # An earlier image was removed while the companion kept running. Export its live
   # read-only code filesystem for rollback; mounted database/runtime data is excluded.
   export=stage/(service+'-rollback-rootfs.tar')
   docker('export','-o',str(export),'bettafish-'+service)
   config=item['Config'];changes=[]
   for entry in config.get('Env') or []:
    key,value=entry.split('=',1);changes+=['--change','ENV '+key+'='+json.dumps(value,ensure_ascii=False)]
   for key,instruction in [('Cmd','CMD'),('Entrypoint','ENTRYPOINT')]:
    if config.get(key) is not None:changes+=['--change',instruction+' '+json.dumps(config[key])]
   if config.get('WorkingDir'):changes+=['--change','WORKDIR '+config['WorkingDir']]
   if config.get('User'):changes+=['--change','USER '+config['User']]
   for port in config.get('ExposedPorts') or {}:changes+=['--change','EXPOSE '+port]
   docker('import',*changes,str(export),tag)
   assert export.resolve().is_relative_to(stage.resolve());export.unlink()
 companions[service]={'image_id':item['Image'],'base_image':tag}
manifest={'name':'NAME','stage':str(stage),'base_image_id':current,'base_image':base,'candidate_image':candidate,
          'candidate_image_id':docker('image','inspect',candidate,'--format','{{.Id}}').decode().strip(),'files':items,'companions':companions,'activated':False}
(stage/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
rollback_config=stage/'rollback-services.json'
rollback_config.write_text(json.dumps({'services':{'bettafish':{'image':base},**{k:{'image':v['base_image']} for k,v in companions.items()}}}))
compose='sudo -n docker compose -f '+str(root/'docker-compose.yml')+' -f '+str(root/'docker-compose.override.yml')+' -f '+str(rollback_config)+' up -d --no-build --no-deps --force-recreate bettafish collection-api collection-worker\n'
rollback='#!/bin/sh\nset -eu\n'
for i in items:
 if i['path'].startswith('tests/'):continue
 target=root/i['path'];assert target.resolve().is_relative_to(root.resolve())
 if i['host_existed']:rollback+='cp '+shlex.quote(str(stage/'host-backup'/i['path']))+' '+shlex.quote(str(target))+'\n'
 else:rollback+='rm -f -- '+shlex.quote(str(target))+'\n'
rollback+='if [ -f '+str(stage/'Dockerfile.local.before')+' ]; then cp '+str(stage/'Dockerfile.local.before')+' '+str(root/'Dockerfile.local')+'; fi\n'
rollback+='sudo -n docker tag '+base+' bettafish:local\n'+compose
(stage/'rollback.sh').write_text(rollback)
print(json.dumps(manifest,ensure_ascii=False))
'''.replace('NAME',name).replace('ITEMS',repr(items)).replace('PAYLOAD',repr(base64.b64encode(payload.getvalue()).decode()))
else:
 script=r'''
import pathlib,subprocess,json,hashlib,time,urllib.request
root=pathlib.Path('/home/ubuntu/bettafish');stage=root/'deploy/NAME';m=json.loads((stage/'release-manifest.json').read_text())
def docker(*args):return subprocess.check_output(['sudo','-n','docker',*args])
def inspect(name):return json.loads(docker('inspect',name))[0]
before=inspect('bettafish');db=inspect('bettafish-db')
companions={k:inspect('bettafish-'+k) for k in m['companions']}
for k,v in companions.items():assert v['Image']==m['companions'][k]['image_id'],'Companion changed: '+k
assert before['Image']==m['base_image_id'],'Running version changed'
for i in m['files']:
 if i['candidate_sha256'] is not None:
  assert hashlib.sha256((stage/'files'/i['path']).read_bytes()).hexdigest()==i['candidate_sha256']
 live=subprocess.run(['sudo','-n','docker','exec','bettafish','cat','/app/'+i['path']],capture_output=True)
 assert (hashlib.sha256(live.stdout).hexdigest() if live.returncode==0 else None)==i['before_sha256']
guard_code="""import json,hashlib
from pathlib import Path
from CampusPulse import weekly,pipeline
from utils.research_runner import active_research_tasks,all_engines_completed
from utils.task_runtime import list_task_ids
import urllib.request,time
for _ in range(3):
 with urllib.request.urlopen('http://127.0.0.1:5000/pulse/api/status',timeout=10) as response:waiting=json.load(response)
 if not waiting.get('running') and not waiting.get('enriching'):break
 time.sleep(20)
with urllib.request.urlopen('http://127.0.0.1:5000/pulse/api/status',timeout=10) as response:collect_state=json.load(response)
assert not collect_state['running'],'Active collection: deployment stopped before changes'
assert not collect_state.get('enriching'),'Active enrichment: deployment stopped before changes'
assert not active_research_tasks(),'Active research: deployment stopped before changes'
assert not any(r['status']=='generating' or r['send_state']=='sending' for r in weekly.recent()),'Active weekly: deployment stopped before changes'
for job in list_task_ids():
 if not all_engines_completed(job):continue
 for _ in range(13):
  with urllib.request.urlopen('http://127.0.0.1:5000/api/report/status?research_task_id='+job,timeout=5) as response:state=json.load(response)
  if (state.get('current_task') or {}).get('status') not in ('pending','running'):break
  time.sleep(20)
 assert (state.get('current_task') or {}).get('status') not in ('pending','running'),'Active final report: deployment stopped before changes'
from CampusPulse import storage
batch=storage.latest_batch('complete')
assert batch and batch['status']=='complete','No durable completed batch'
raw=storage.load_batch_items(batch['batch_ts'])
assert raw,'Raw collection checkpoint missing'
cfg=weekly.config(True)
print(json.dumps({'raw_batch':batch['batch_ts'],'raw_digest':hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest(),'config_digest':hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest(),'environment_digest':hashlib.sha256(Path('/app/.env').read_bytes()).hexdigest()}))
"""
# Mandatory preflight lives inside activation, rather than relying on caller sequencing.
preflight=json.loads(docker('exec','bettafish','python','-c',guard_code))
(stage/'activation-preflight.json').write_text(json.dumps(preflight))
try:
 for i in m['files']:
  if i['path'].startswith('tests/'):continue
  target=root/i['path'];assert target.resolve().is_relative_to(root.resolve())
  if i['candidate_sha256'] is None:target.unlink(missing_ok=True)
  else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((stage/'files'/i['path']).read_bytes())
 (root/'Dockerfile.local').write_bytes((stage/'files/Dockerfile.local').read_bytes())
 docker('tag',m['candidate_image'],'bettafish:local')
 p=subprocess.run(['sudo','-n','docker','compose','-f',str(root/'docker-compose.yml'),'-f',str(root/'docker-compose.override.yml'),'up','-d','--no-build','--no-deps','--force-recreate','bettafish','collection-api','collection-worker'],capture_output=True,timeout=300)
 assert p.returncode==0,'Application recreation failed'
 ready=False
 for _ in range(90):
  try:
   ready=urllib.request.urlopen('http://127.0.0.1:5000/login',timeout=3).status==200
   if ready:break
  except Exception:pass
  time.sleep(1)
 assert ready,'Application not ready'
 after=inspect('bettafish');db_after=inspect('bettafish-db')
 assert db_after['Id']==db['Id'] and db_after['State']['StartedAt']==db['State']['StartedAt']
 assert before['Mounts']==after['Mounts']
 for k,old in companions.items():
  new=inspect('bettafish-'+k)
  assert old['Mounts']==new['Mounts'] and new['Image']==m['candidate_image_id']
  assert old['Config']['Cmd']==new['Config']['Cmd'] and dict(v.split('=',1) for v in old['Config']['Env'])==dict(v.split('=',1) for v in new['Config']['Env']),'Companion configuration changed: '+k
 assert after['Image']==m['candidate_image_id']
 for i in m['files']:
  result=subprocess.run(['sudo','-n','docker','exec','bettafish','cat','/app/'+i['path']],capture_output=True)
  assert (hashlib.sha256(result.stdout).hexdigest() if result.returncode==0 else None)==i['candidate_sha256']
 verify_code="import json,hashlib;from pathlib import Path;from CampusPulse import weekly,storage;p="+repr(preflight)+";assert hashlib.sha256(Path('/app/.env').read_bytes()).hexdigest()==p['environment_digest'];assert hashlib.sha256(json.dumps(weekly.config(True),sort_keys=True).encode()).hexdigest()==p['config_digest'];assert hashlib.sha256(json.dumps(storage.load_batch_items(p['raw_batch']),sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()==p['raw_digest'];print('verified')"
 assert docker('exec','bettafish','python','-c',verify_code).decode().strip()=='verified'
 m['activated']=True;(stage/'release-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 print(json.dumps({'activated':True,'image_id':after['Image'],'database_unchanged':True,'mounts_unchanged':True,'files_verified':len(m['files'])}))
except Exception:
 subprocess.run(['sh',str(stage/'rollback.sh')],capture_output=True,timeout=300)
 raise
'''.replace('NAME',name)
if mode=='activate-with-checkpoint':
 script=script.replace("assert not collect_state.get('enriching'),'Active enrichment: deployment stopped before changes'","assert collect_state.get('last_fetch_status') != 'fetched','Uncommitted raw collection'")
 # Skip optional enrichment only after a complete durable raw batch is verified above.
 script=script.replace("and not waiting.get('enriching')",'')
result=subprocess.run(ssh,input=script.encode(),capture_output=True,timeout=900)
if result.returncode:
 err=result.stderr.decode(errors='replace');print('\n'.join(line for line in err.splitlines() if 'AssertionError:' in line));print(err[-500:]);raise SystemExit(result.returncode)
data=json.loads(result.stdout)
prefix='references'
dest=repo/'validation'/(prefix+('-release-manifest.json' if mode=='prepare' else '-deployment-result.json'))
dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
