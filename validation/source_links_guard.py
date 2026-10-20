"""Read-only Resend checks; keep keys inside the running container, never send mail."""
import pathlib,subprocess,json,shlex,sys
repo=pathlib.Path(__file__).resolve().parents[1];mode=sys.argv[1]
code=r"""
import json,hashlib,urllib.request
from CampusPulse import weekly
cfg=weekly.config(True)
active=[r['id'] for r in weekly.recent() if r['status']=='generating' or r['send_state']=='sending']
result={'config_digest':hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest(),'environment_digest':hashlib.sha256(__import__('pathlib').Path('/app/.env').read_bytes()).hexdigest(),'active_weeklies':len(active),'key_configured':bool(cfg['api_key']),'automatic_enabled':cfg['enabled']}
if MODE=='after':
 with urllib.request.urlopen('https://smydashuaige.2026515.xyz/login',timeout=25) as response:result['website_http']=response.status
print(json.dumps(result))
""".replace('MODE',repr(mode))
remote=r"""
import subprocess,json,pathlib
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/source-links-20261020')
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish','python','-'],input=CODE.encode(),capture_output=True,timeout=65)
if r.returncode:raise RuntimeError('Read-only configuration check failed')
data=json.loads(r.stdout)
if MODE=='before':
 assert data['active_weeklies']==0,'Weekly task is active; wait before restart'
 (stage/'config-guard.json').write_text(json.dumps(data))
else:
 before=json.loads((stage/'config-guard.json').read_text());assert before['config_digest']==data['config_digest'],'Mail configuration changed'
 assert before['environment_digest']==data['environment_digest'],'External service environment changed'
 data['configuration_unchanged']=True
 data['emails_sent']=0
 data['passed']=data['website_http']==200
 assert data['passed']
data.pop('config_digest');data.pop('environment_digest');print(json.dumps(data))
""".replace('CODE',repr(code)).replace('MODE',repr(mode))
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3 -'],input=remote.encode(),capture_output=True,timeout=90)
if r.returncode:print(r.stderr.decode(errors='replace')[-700:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
if mode=='after':(repo/'validation/source-links-config-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data))
