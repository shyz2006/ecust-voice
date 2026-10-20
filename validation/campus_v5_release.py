"""Prepare an immutable candidate and activate with source/image/data guards."""
import base64,hashlib,io,json,pathlib,subprocess,sys,tarfile
repo=pathlib.Path(__file__).resolve().parent.parent
name='campus-weekly-20261020'
paths=['templates/index.html','CampusPulse/templates/pulse.html','static/js/campus-review.js','static/js/campus-weekly.js','static/css/campus-play.css','CampusPulse/blueprint.py','CampusPulse/weekly.py']
ssh=[r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@3.17.59.150','python3 -']
mode=sys.argv[1] if len(sys.argv)>1 else 'prepare'
if mode=='prepare':
 items=[];payload=io.BytesIO()
 with tarfile.open(fileobj=payload,mode='w:gz') as archive:
  for p in paths:
   old=subprocess.run(['git','show','cbfcc66:production/'+p],cwd=repo,capture_output=True)
   items.append({'path':p,'candidate_sha256':hashlib.sha256((repo/'production'/p).read_bytes()).hexdigest(),
                 'expected_before':hashlib.sha256(old.stdout).hexdigest() if old.returncode==0 else None})
   archive.add(repo/'production'/p,arcname=p)
  archive.add(repo/'host-deployment/Dockerfile.local',arcname='Dockerfile.local')
 script=r'''
import pathlib,subprocess,json,hashlib,tarfile,io,base64,shlex
root=pathlib.Path('/home/ubuntu/bettafish');stage=root/'deploy/NAME';items=ITEMS
def docker(*args):return subprocess.check_output(['sudo','-n','docker',*args])
current=docker('inspect','bettafish','--format','{{.Image}}').decode().strip()
if stage.exists():
 old=json.loads((stage/'release-manifest.json').read_text());assert not old['activated'] and old['base_image_id']==current,'Release already active or base changed'
blobs={}
for item in items:
 p=item['path'];live=subprocess.run(['sudo','-n','docker','exec','bettafish','cat','/app/'+p],capture_output=True)
 assert (live.returncode==0)==(item['expected_before'] is not None),'Unexpected baseline file: '+p
 item['before_sha256']=hashlib.sha256(live.stdout).hexdigest() if live.returncode==0 else None
 assert item['before_sha256']==item['expected_before'],'Running source changed: '+p
 blobs[p]=live.stdout if live.returncode==0 else None
 host=root/p;item['host_existed']=host.exists()
 if host.exists():assert hashlib.sha256(host.read_bytes()).hexdigest()==item['before_sha256'],'Host drift: '+p
stage.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(PAYLOAD)),mode='r:gz') as a:a.extractall(stage/'files',filter='data')
for p,data in blobs.items():
 if data is not None:
  backup=stage/'backup'/p;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(data)
if (root/'Dockerfile.local').exists():(stage/'Dockerfile.local.before').write_bytes((root/'Dockerfile.local').read_bytes())
base='bettafish:base-NAME';candidate='bettafish:candidate-NAME';docker('tag',current,base)
(stage/'Dockerfile').write_text('FROM '+base+'\nWORKDIR /app\nRUN apt-get update -qq && apt-get install -y --no-install-recommends fonts-noto-cjk && rm -rf /var/lib/apt/lists/*\n'+''.join('COPY '+json.dumps(['files/'+i['path'],'/app/'+i['path']],ensure_ascii=False)+'\n' for i in items))
build=subprocess.run(['sudo','-n','docker','build','--pull=false','-t',candidate,str(stage)],capture_output=True)
assert build.returncode==0,build.stderr.decode(errors='replace')[-500:]
for i in items:
 data=docker('run','--rm','--network','none','--entrypoint','cat',candidate,'/app/'+i['path'])
 assert hashlib.sha256(data).hexdigest()==i['candidate_sha256']
manifest={'name':'NAME','stage':str(stage),'base_image_id':current,'base_image':base,'candidate_image':candidate,
          'candidate_image_id':docker('image','inspect',candidate,'--format','{{.Id}}').decode().strip(),'files':items,'activated':False}
(stage/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
compose='sudo -n docker compose -f '+str(root/'docker-compose.yml')+' -f '+str(root/'docker-compose.override.yml')+' up -d --no-deps --force-recreate bettafish\n'
rollback='#!/bin/sh\nset -eu\n'
for i in items:
 target=root/i['path'];assert target.resolve().is_relative_to(root.resolve())
 if i['host_existed']:rollback+='cp '+shlex.quote(str(stage/'backup'/i['path']))+' '+shlex.quote(str(target))+'\n'
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
assert before['Image']==m['base_image_id'],'Running version changed'
for i in m['files']:
 assert hashlib.sha256((stage/'files'/i['path']).read_bytes()).hexdigest()==i['candidate_sha256']
 live=subprocess.run(['sudo','-n','docker','exec','bettafish','cat','/app/'+i['path']],capture_output=True)
 assert (hashlib.sha256(live.stdout).hexdigest() if live.returncode==0 else None)==i['before_sha256']
try:
 for i in m['files']:
  target=root/i['path'];assert target.resolve().is_relative_to(root.resolve());target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((stage/'files'/i['path']).read_bytes())
 (root/'Dockerfile.local').write_bytes((stage/'files/Dockerfile.local').read_bytes())
 docker('tag',m['candidate_image'],'bettafish:local')
 p=subprocess.run(['sudo','-n','docker','compose','-f',str(root/'docker-compose.yml'),'-f',str(root/'docker-compose.override.yml'),'up','-d','--no-deps','--force-recreate','bettafish'],capture_output=True,timeout=90)
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
 assert after['Image']==m['candidate_image_id']
 for i in m['files']:assert hashlib.sha256(docker('exec','bettafish','cat','/app/'+i['path'])).hexdigest()==i['candidate_sha256']
 m['activated']=True;(stage/'release-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 print(json.dumps({'activated':True,'image_id':after['Image'],'database_unchanged':True,'mounts_unchanged':True,'files_verified':len(m['files'])}))
except Exception:
 subprocess.run(['sh',str(stage/'rollback.sh')],capture_output=True,timeout=90)
 raise
'''.replace('NAME',name)
result=subprocess.run(ssh,input=script.encode(),capture_output=True,timeout=300)
if result.returncode:print(result.stderr.decode(errors='replace')[-1500:]);raise SystemExit(result.returncode)
data=json.loads(result.stdout)
prefix='campus-v5'
dest=repo/'validation'/(prefix+('-release-manifest.json' if mode=='prepare' else '-deployment-result.json'))
dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
