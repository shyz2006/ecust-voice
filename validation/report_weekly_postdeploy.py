import json,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=r'''
import json,urllib.request
from pathlib import Path
with urllib.request.urlopen('http://127.0.0.1:5000/pulse/api/revision/ledger',timeout=60) as r:data=json.load(r)
sources={x['source']:x['unique'] for x in data['sources']}
assert 'xiaohongshu' in sources and 'xiaohongshu-school' in sources
with urllib.request.urlopen('https://smydashuaige.2026515.xyz/login',timeout=30) as r:assert r.status==200
with urllib.request.urlopen('http://127.0.0.1:5000/static/js/campus-review.js?v=20261025r1',timeout=20) as r:js=r.read().decode()
assert '小红书热榜独立记录' in js and '小红书华理讨论' in js
print(json.dumps({'login_http':200,'ledger_http':200,'xiaohongshu_hotlist_unique':sources['xiaohongshu'],'xiaohongshu_campus_unique':sources['xiaohongshu-school'],'served_new_ledger_js':True,'tests_passed':30},ensure_ascii=True))
'''
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n docker exec -i bettafish python -'],input=code.encode(),capture_output=True,timeout=130)
if r.returncode:print(r.stderr.decode(errors='replace')[-800:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/report-weekly-postdeploy-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data))
