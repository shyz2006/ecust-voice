import subprocess,pathlib,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=pathlib.Path(__file__).resolve().parent.parent
remote=r'''
import subprocess,json
code="""import pathlib,json
roots=list(pathlib.Path('/tmp').glob('teacher-validation-*'))
root=roots[-1]/'runtime'
for p in root.rglob('*.log'):
 print(str(p.relative_to(root)))
 lines=p.read_text(errors='replace').splitlines()
 progress=[line for line in lines if '[后台研究] 段落 ' in line]
 if progress:print(progress[-1])
 for line in lines[-3:]:
  if not any(w in line.lower() for w in ('api_key','authorization','bearer ','secret','password')):print(line[:450])
"""
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish-teacher-validation','python','-'],input=code.encode(),capture_output=True)
print(r.stdout.decode(errors='replace'))
stats=subprocess.check_output(['sudo','-n','docker','stats','--no-stream','--format','{{.Name}} {{.MemUsage}} {{.CPUPerc}}','bettafish-teacher-validation','bettafish']).decode()
print(stats)
'''
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3','-'],input=remote.encode(),capture_output=True,timeout=40)
print(r.stdout.decode(errors='replace'))
