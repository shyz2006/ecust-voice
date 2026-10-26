import subprocess,sys,json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1]).read_bytes()
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@3.17.59.150','sudo -n docker exec -i bettafish python -'],input=source,capture_output=True,timeout=180)
if r.returncode:print(r.stderr.decode(errors='replace')[-1200:]);raise SystemExit(r.returncode)
if len(sys.argv)>2:
 Path(sys.argv[2]).write_text(json.dumps(json.loads(r.stdout),ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(r.stdout.decode(errors='replace'))
