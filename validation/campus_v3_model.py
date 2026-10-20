"""Apply the validated free report route; preserve keys and restore model fields on rollback."""
import pathlib,subprocess,json
repo=pathlib.Path(__file__).resolve().parents[1]
remote=r'''
import pathlib,json,shutil,os
root=pathlib.Path('/home/ubuntu/bettafish');stage=root/'deploy/campus-polish-20261020';env=root/'.env'
updates={'REPORT_ENGINE_MODEL_NAME':'minimax/minimax-m3.1-flash:free','LLM_FALLBACK_MODELS':'poolside/laguna-s-2.1-free,minimax/minimax-m3.1-flash:free'}
text=env.read_text();lines=text.splitlines()
def parse(rows):
 return {line.split('=',1)[0].strip():line.split('=',1)[1].strip() for line in rows if '=' in line and not line.lstrip().startswith('#')}
values=parse(lines);assert values.get('REPORT_ENGINE_MODEL_NAME','').strip(chr(34)+chr(39))=='poolside/laguna-s-2.1-free','Model configuration changed; do not overwrite it'
secure=stage/'secure-config-before';secure.mkdir(mode=0o700,exist_ok=True);os.chmod(secure,0o700)
(secure/'.gitignore').write_text('*'+chr(10))
backup=secure/'env.before';assert not backup.exists(),'Model update already prepared'
shutil.copy2(env,backup);os.chmod(backup,0o600)
before={key:values.get(key) for key in updates}
(stage/'model-before.json').write_text(json.dumps(before))
def replace(rows,fields):
 seen=set();out=[]
 for line in rows:
  key=line.split('=',1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else ''
  if key in fields:out.append(key+'='+fields[key]);seen.add(key)
  else:out.append(line)
 for key,value in fields.items():
  if key not in seen:out.append(key+'='+value)
 return out
changed=replace(lines,updates)
assert {k:v for k,v in parse(changed).items() if k not in updates}=={k:v for k,v in values.items() if k not in updates}
restore="""import pathlib,json
root=pathlib.Path('/home/ubuntu/bettafish');env=root/'.env'
before=json.loads((root/'deploy/campus-polish-20261020/model-before.json').read_text())
out=[];seen=set()
for line in env.read_text().splitlines():
 key=line.split('=',1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else ''
 if key in before:
  if before[key] is not None:out.append(key+'='+before[key])
  seen.add(key)
 else:out.append(line)
for key,value in before.items():
 if key not in seen and value is not None:out.append(key+'='+value)
env.write_text(chr(10).join(out)+chr(10))
"""
compile(restore,str(stage/'restore-model.py'),'exec');(stage/'restore-model.py').write_text(restore)
rollback=stage/'rollback.sh';content=rollback.read_text();assert '# campus-v3 model restore' not in content
assert 'set -eu'+chr(10) in content
rollback.write_text(content.replace('set -eu'+chr(10),'set -eu'+chr(10)+'# campus-v3 model restore'+chr(10)+'python3 '+str(stage/'restore-model.py')+chr(10),1))
env.write_text(chr(10).join(changed)+chr(10))
print(json.dumps({'report_model_before':before['REPORT_ENGINE_MODEL_NAME'],'report_model_after':updates['REPORT_ENGINE_MODEL_NAME'],
 'fallback_models':updates['LLM_FALLBACK_MODELS'],'api_keys_and_other_fields_unchanged':True,'secure_backup_on_server':True,'rollback_restores_only_model_fields':True}))
'''
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3 -'],input=remote.encode(),capture_output=True,timeout=45)
if r.returncode:print(r.stderr.decode(errors='replace')[-1000:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/campus-v3-model-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data))
