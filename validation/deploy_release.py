"""Activate a verified prepared release only when deployment is authorized."""
import pathlib,subprocess,json,os
repo=pathlib.Path(__file__).resolve().parent.parent
script=r'''
import pathlib,json,subprocess,hashlib,time,urllib.request,urllib.error,datetime
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/workshop-question-entry-20261012-411d0c7')
root=pathlib.Path('/home/ubuntu/bettafish');manifest=json.loads((stage/'release-manifest.json').read_text())
def docker(*args):return subprocess.check_output(['sudo','-n','docker',*args])
def inspect(name):return json.loads(docker('inspect',name))[0]
before=inspect('bettafish');db_before=inspect('bettafish-db')
assert before['Image']==manifest['base_image_id'], 'Running image changed'
assert docker('image','inspect',manifest['candidate_image'],'--format','{{.Id}}').decode().strip()==manifest['candidate_image_id'], 'Candidate image changed'
for item in manifest['files']:
 p=item['path']
 assert hashlib.sha256((stage/'files'/p).read_bytes()).hexdigest()==item['candidate_sha256'], 'Staged code changed'
 assert hashlib.sha256((root/p).read_bytes()).hexdigest()==item['before_sha256'], 'Host code changed'
 assert hashlib.sha256(docker('exec','bettafish','cat','/app/'+p)).hexdigest()==item['before_sha256'], 'Container code changed'
 assert hashlib.sha256((stage/'backup'/p).read_bytes()).hexdigest()==item['before_sha256'], 'Rollback source changed'
result={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'activated':False}
try:
 activation=subprocess.run(['sh',str(stage/'activate.sh')],capture_output=True,timeout=90)
 assert activation.returncode==0, 'Container recreation failed'
 deadline=time.monotonic()+60;ready=False
 while time.monotonic()<deadline:
  try:
   with urllib.request.urlopen('http://127.0.0.1:5000/login',timeout=4) as response:
    ready=response.status==200 and b'<html' in response.read().lower()
  except (OSError,urllib.error.URLError):pass
  if ready:break
  time.sleep(2)
 assert ready, 'Application did not become ready'
 after=inspect('bettafish');db_after=inspect('bettafish-db')
 assert after['Image']==manifest['candidate_image_id'], 'Unexpected deployed image'
 assert after['Mounts']==before['Mounts'], 'Application mounts changed'
 assert db_after['Id']==db_before['Id'] and db_after['State']['StartedAt']==db_before['State']['StartedAt'], 'Database was recreated or restarted'
 for item in manifest['files']:
  assert hashlib.sha256(docker('exec','bettafish','cat','/app/'+item['path'])).hexdigest()==item['candidate_sha256'], 'Deployed source mismatch'
 result.update({'activated':True,'image_id':after['Image'],'application_ready':True,'database_unchanged':True,'mounts_unchanged':True,'verified_files':len(manifest['files'])})
except Exception as exc:
 rollback=subprocess.run(['sh',str(stage/'rollback.sh')],capture_output=True,timeout=90)
 result.update({'failure':str(exc),'rollback_exit_code':rollback.returncode})
manifest.update(result);(stage/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
(stage/'deployment-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result))
'''.replace('workshop-question-entry-20261012-411d0c7',os.getenv('WORKSHOP_RELEASE_NAME','workshop-question-entry-20261012-411d0c7'))
key=repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'
result=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(key),'-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@3.144.33.23','python3 -'],input=script.encode(),capture_output=True,timeout=230)
if result.returncode:
 print(result.stderr.decode(errors='replace')[-1200:]);raise SystemExit(result.returncode)
data=json.loads(result.stdout)
(repo.parent/'validation-artifacts/deployment-result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
if not data.get('activated'):raise SystemExit(1)
