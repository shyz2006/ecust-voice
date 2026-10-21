"""Start/stop isolated candidate service. The existing app and database remain running."""
import pathlib,subprocess,base64,sys,json
repo=pathlib.Path(__file__).resolve().parent.parent
action=sys.argv[1] if len(sys.argv)>1 else 'start'
if action=='start':
 data=base64.b64encode((repo/'validation/campus_v3_candidate_server.py').read_bytes()).decode()
 script=r'''
import subprocess,pathlib,base64,json,time,urllib.request
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/workshop-intent-20261021')
name='bettafish-workshop-intent-validation'
previous=subprocess.run(['sudo','-n','docker','inspect',name],capture_output=True)
assert previous.returncode!=0,'Validation container already exists'
(stage/'validation-runtime').mkdir(exist_ok=True)
(stage/'validation_server.py').write_bytes(base64.b64decode(PAYLOAD))
r=subprocess.run(['sudo','-n','docker','run','-d','--name',name,'--network','host','--volumes-from','bettafish:ro',
 '-e','DB_HOST=127.0.0.1','-e','DB_PORT=5444',
 '--memory','1800m','--memory-swap','3g','--cpus','1','-v',str(stage/'validation_server.py')+':/tmp/validation_server.py:ro',
 '--entrypoint','python','bettafish:candidate-workshop-intent-20261021','/tmp/validation_server.py'],capture_output=True)
assert r.returncode==0,r.stderr.decode(errors='replace')[-500:]
ready=False
for i in range(100):
 try:
  ready=json.load(urllib.request.urlopen('http://127.0.0.1:15003/validation/health',timeout=2)).get('isolated') is True
  if ready:break
 except Exception:pass
 time.sleep(1)
if not ready:
 logs=subprocess.check_output(['sudo','-n','docker','logs','--tail','12',name],stderr=subprocess.STDOUT).decode(errors='replace')
 print(logs[-1800:]);raise SystemExit(1)
print(json.dumps({'ready':True,'database':'temporary copy','runtime':'temporary','container':name}))
'''.replace('PAYLOAD',repr(data))
else:
 script="import subprocess;subprocess.run(['sudo','-n','docker','stop','-t','15','bettafish-workshop-intent-validation'],check=True);subprocess.run(['sudo','-n','docker','rm','bettafish-workshop-intent-validation'],check=True)"
if len(sys.argv)>2 and sys.argv[2]=='web':
 script=script.replace('bettafish-workshop-intent-validation','bettafish-workshop-intent-validation-web').replace('15003','15004')
 script=script.replace("'--memory','1800m'","'-e','VALIDATION_PORT=15004','--memory','700m'")
if len(sys.argv)>2 and sys.argv[2]=='resume':
 script=script.replace("'--memory','1800m'","'-e','VALIDATION_RUNTIME_DIR=/tmp/validation-runtime','-v',str(stage/'validation-runtime')+':/tmp/validation-runtime','--memory','1800m'")
result=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3 -'],input=script.encode(),capture_output=True,timeout=150)
print(result.stdout.decode(errors='replace'))
if result.returncode:print(result.stderr.decode(errors='replace')[-1600:]);raise SystemExit(result.returncode)
