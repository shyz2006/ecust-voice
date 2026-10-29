import subprocess,json,re
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code="""import unittest,sys
loader=unittest.TestLoader()
suite=loader.discover('tests',pattern='test_*.py')
r=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not r.wasSuccessful())
"""
remote='import subprocess,sys\nr=subprocess.run('+repr(['sudo','-n','docker','run','--rm','--network','none','--entrypoint','python','bettafish:candidate-event-report-20261030-r1','-c',code])+',capture_output=True,timeout=120)\nsys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)\n'
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n python3 -'],input=remote.encode(),capture_output=True,timeout=150)
text=r.stderr.decode(errors='replace');print(text[-9000:]);matches=re.findall(r'Ran (\d+) tests',text)
result={'passed':r.returncode==0,'tests':int(matches[-1]) if matches else 0,'network':'disabled','model_calls':0,'emails_sent':0}
(repo/'validation/event-report-test-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result));raise SystemExit(r.returncode)
