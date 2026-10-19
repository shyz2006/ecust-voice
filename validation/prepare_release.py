"""Prepare isolated image and rollback artifacts; do not activate production."""
import pathlib,subprocess,base64,tarfile,io,json,hashlib,os
repo=pathlib.Path(__file__).resolve().parent.parent
paths=os.getenv('WORKSHOP_RELEASE_FILES','templates/index.html,CampusPulse/templates/pulse.html,CampusPulse/agents/analysis_options.py,CampusPulse/agents/orchestrator.py,CampusPulse/campus.py,CampusPulse/blueprint.py,CampusPulse/memes.py').split(',')
ssh_host=os.getenv('WORKSHOP_SSH_HOST','ubuntu@3.17.59.150')
release_name=os.getenv('WORKSHOP_RELEASE_NAME','network-memes-20261018')
manifest=[{'path':p,'candidate_sha256':hashlib.sha256((repo/'production'/p).read_bytes()).hexdigest()} for p in paths]
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
 for p in paths: archive.add(repo/'production'/p,arcname=p)
script=r'''
import pathlib,subprocess,json,hashlib,base64,tarfile,io,shlex
root=pathlib.Path('/home/ubuntu/bettafish')
stage=root/'deploy/workshop-question-entry-20261012-411d0c7'
items=MANIFEST
def docker(*args):return subprocess.check_output(['sudo','-n','docker',*args])
image_id=docker('inspect','bettafish','--format','{{.Image}}').decode().strip()
live_blobs={}
for item in items:
 live=docker('exec','bettafish','cat','/app/'+item['path'])
 item['before_sha256']=hashlib.sha256(live).hexdigest()
 live_blobs[item['path']]=live
assert not stage.exists(), 'Release staging directory already exists'
stage.mkdir(parents=True)
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(PAYLOAD))) as archive:archive.extractall(stage/'files',filter='data')
for item in items:
 dest=stage/'backup'/item['path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(live_blobs[item['path']])
base='bettafish:workshop-base-20261012-411d0c7';candidate='bettafish:workshop-candidate-20261012-411d0c7'
docker('tag',image_id,base)
dockerfile='FROM '+base+'\nWORKDIR /app\n'+''.join('COPY files/'+item['path']+' /app/'+item['path']+'\n' for item in items)
(stage/'Dockerfile').write_text(dockerfile)
build=subprocess.run(['sudo','-n','docker','build','--pull=false','-t',candidate,str(stage)],capture_output=True)
if build.returncode:raise RuntimeError('Candidate image build failed')
docker('run','--rm','--network','none','--entrypoint','python',candidate,'-c',"import py_compile;py_compile.compile('/app/CampusPulse/agents/analysis_options.py',doraise=True);py_compile.compile('/app/CampusPulse/agents/orchestrator.py',doraise=True);from CampusPulse.agents import analysis_options,router;assert analysis_options.prompt({'analysis_options':{'thinking_effort':'auto','psych_lens':'none','ideology':'none'}})==''")
for item in items:
 data=docker('run','--rm','--network','none','--entrypoint','cat',candidate,'/app/'+item['path'])
 assert hashlib.sha256(data).hexdigest()==item['candidate_sha256']
metadata={'stage':str(stage),'base_image':base,'base_image_id':image_id,'candidate_image':candidate,'candidate_image_id':docker('image','inspect',candidate,'--format','{{.Id}}').decode().strip(),'files':items,'activated':False}
(stage/'release-manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
iptables_guard='sudo -n iptables -t filter -N DOCKER 2>/dev/null || true\nsudo -n iptables -t filter -N DOCKER-ISOLATION-STAGE-1 2>/dev/null || true\nsudo -n iptables -t filter -N DOCKER-ISOLATION-STAGE-2 2>/dev/null || true\nsudo -n iptables -t filter -N DOCKER-USER 2>/dev/null || true\nsudo -n iptables -t nat -N DOCKER 2>/dev/null || true\n'
compose='sudo -n docker compose -f '+str(root/'docker-compose.yml')+' -f '+str(root/'docker-compose.override.yml')+' up -d --no-deps --force-recreate bettafish\n'
activate='#!/bin/sh\nset -eu\ncd '+str(root)+'\n'+iptables_guard
activate+='test "$(sudo -n docker inspect bettafish --format \'{{.Image}}\')" = '+shlex.quote(image_id)+'\n'
for item in items:activate+='cp '+shlex.quote(str(stage/'files'/item['path']))+' '+shlex.quote(str(root/item['path']))+'\n'
activate+='sudo -n docker tag '+candidate+' bettafish:local\n'+compose
(stage/'activate.sh').write_text(activate)
rollback='#!/bin/sh\nset -eu\ncd '+str(root)+'\n'+iptables_guard
for item in items:rollback+='cp '+shlex.quote(str(stage/'backup'/item['path']))+' '+shlex.quote(str(root/item['path']))+'\n'
rollback+='sudo -n docker tag '+base+' bettafish:local\n'+compose
(stage/'rollback.sh').write_text(rollback)
assert docker('inspect','bettafish','--format','{{.Image}}').decode().strip()==image_id
print(json.dumps(metadata))
'''.replace('workshop-question-entry-20261012-411d0c7',release_name).replace('workshop-base-20261012-411d0c7','base-'+release_name).replace('workshop-candidate-20261012-411d0c7','candidate-'+release_name).replace('MANIFEST',repr(manifest)).replace('PAYLOAD',repr(base64.b64encode(buffer.getvalue()).decode()))
key=repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'
result=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(key),'-o','BatchMode=yes',ssh_host,'python3 -'],input=script.encode(),capture_output=True,timeout=120)
if result.returncode:
 print(result.stderr.decode(errors='replace')[-1500:]);raise SystemExit(1)
metadata=json.loads(result.stdout)
out=repo.parent/'validation-artifacts';(out/'release-manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(metadata,ensure_ascii=False))


