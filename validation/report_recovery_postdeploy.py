"""Read-only deployment checks without manufacturing a browser session."""
import pathlib,subprocess,shlex,json
repo=pathlib.Path(__file__).resolve().parents[1]
manifest=json.loads((repo/'validation/report-recovery-release-manifest.json').read_text(encoding='utf-8'))
expected={i['path']:i['candidate_sha256'] for i in manifest['files']}
code=r"""
import hashlib,json,urllib.request
from pathlib import Path
expected=EXPECTED
assert all(hashlib.sha256((Path('/app')/p).read_bytes()).hexdigest()==v for p,v in expected.items())
assert (Path('/app/templates/index.html').read_bytes()==Path('/app/CampusPulse/templates/pulse.html').read_bytes())
html=Path('/app/templates/index.html').read_text();assert html.count('class="workshop-tab-icon"')==2 and '校园周报 ✉' not in html and '20261022p1' in html
with urllib.request.urlopen('https://smydashuaige.2026515.xyz/login',timeout=30) as r:assert r.status==200
assets=[]
for p in ('static/js/campus-review.js','static/css/campus-play.css'):
 with urllib.request.urlopen('http://127.0.0.1:5000/'+p+'?v=20261022p1',timeout=20) as r:body=r.read()
 assert hashlib.sha256(body).hexdigest()==expected[p];assets.append(p)
with urllib.request.urlopen('http://127.0.0.1:5000/api/report/status',timeout=20) as r:state=json.load(r)
print(json.dumps({'passed':True,'files_verified':len(expected),'root_and_pulse_match':True,'consistent_tab_icons':True,'website_login_http':200,'served_static_hashes':assets,'report_initialized':state['initialized'],'model_calls':0,'search_calls':0,'emails_sent':0}))
""".replace('EXPECTED',repr(expected))
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','exec','-i','bettafish','python','-'])],input=code.encode(),capture_output=True,timeout=140)
if r.returncode:print(r.stderr.decode(errors='replace')[-700:]);raise SystemExit(r.returncode)
value=json.loads(r.stdout);(repo/'validation/report-recovery-postdeploy-results.json').write_bytes((json.dumps(value,indent=2)+'\n').encode());print(json.dumps(value))
