"""Profile one read-model rebuild on a temporary database copy."""
import pathlib,subprocess,shlex
repo=pathlib.Path(__file__).resolve().parent.parent
code=r'''
import tempfile,pathlib,sqlite3,cProfile,pstats,time
from CampusPulse.config import settings
root=pathlib.Path(tempfile.mkdtemp());source=sqlite3.connect('file:'+str(settings.db_path)+'?mode=ro',uri=True)
target=sqlite3.connect(root/'campus.db');source.backup(target);source.close();target.close();settings.db_path=root/'campus.db'
from CampusPulse import revision
profile=cProfile.Profile();profile.enable();data=revision.snapshot(True);profile.disable()
print('Posts:',data['total']);pstats.Stats(profile).strip_dirs().sort_stats('cumtime').print_stats(20)
started=time.monotonic();again=revision.snapshot(True)
print('Rebuild after index and token cache:',round(time.monotonic()-started,3),'seconds; posts:',again['total'])
'''
args=['sudo','-n','docker','run','--rm','-i','--network','none','--volumes-from','bettafish:ro','--memory','800m','--cpus','1','--entrypoint','python','bettafish:candidate-teacher-feedback-20261020','-']
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(args)],input=code.encode(),capture_output=True,timeout=180)
print(r.stdout.decode(errors='replace'));print(r.stderr.decode(errors='replace')[-300:]);raise SystemExit(r.returncode)
