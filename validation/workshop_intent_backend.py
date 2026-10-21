import pathlib,subprocess,json,base64
repo=pathlib.Path(__file__).resolve().parent.parent
script=(repo/'validation/workshop_intent_backend_case.py').read_bytes()
command=['sudo','-n','docker','run','--rm','-i','--network','none','--entrypoint','python','bettafish:candidate-workshop-intent-20261021','-']
import shlex
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(command)],input=script,capture_output=True,timeout=100)
if r.returncode:print(r.stderr.decode(errors='replace')[-2500:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
(repo/'validation/workshop-intent-backend-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
