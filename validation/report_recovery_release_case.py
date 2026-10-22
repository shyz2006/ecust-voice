"""Exercise the actual mandatory preflight extracted from the activation script."""
import ast,json,pathlib,re,sys,types
from unittest.mock import patch
source=pathlib.Path(__file__).with_name('report_recovery_release.py').read_text(encoding='utf-8')
activation=re.findall(r"script=r\'\'\'(.*?)\'\'\'",source,re.S)[-1]
node=next(n for n in ast.walk(ast.parse(activation)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='guard_code' for t in n.targets))
code=ast.literal_eval(node.value)
active=[];weeklies=[];jobs=[]
weekly=types.SimpleNamespace(config=lambda full:{'api_key':'fake-unit-key'},recent=lambda:weeklies)
modules={'CampusPulse':types.SimpleNamespace(weekly=weekly),'utils.research_runner':types.SimpleNamespace(active_research_tasks=lambda:active,all_engines_completed=lambda task:True),'utils.task_runtime':types.SimpleNamespace(list_task_ids=lambda:jobs)}
class FakePath:
 def __init__(self,*args):pass
 def read_bytes(self):return b'fake-unit-environment'
checks=[]
with patch.dict(sys.modules,modules),patch('pathlib.Path',FakePath):
 for task,week in [(['active'],[]),([],[{'status':'generating','send_state':'pending'}]),([],[{'status':'ready','send_state':'sending'}])]:
  active[:]=task;weeklies[:]=week
  try:exec(code,{})
  except AssertionError:checks.append('blocked')
  else:raise AssertionError('Preflight did not stop deployment')
 active.clear();weeklies.clear();printed=[]
 with patch('builtins.print',side_effect=printed.append):exec(code,{})
 value=json.loads(printed[0]);assert set(value)=={'config_digest','environment_digest'} and 'fake-unit-key' not in printed[0]
class Reply:
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self):return json.dumps({'current_task':{'status':'running'}}).encode()
jobs[:]=['task_fixture']
with patch.dict(sys.modules,modules),patch('pathlib.Path',FakePath),patch('urllib.request.urlopen',return_value=Reply()):
 try:exec(code,{})
 except AssertionError as exc:assert 'Active final report' in str(exc)
 else:raise AssertionError('Active final report did not block restart')
jobs.clear()
assert "Active final report" in code
assert activation.index('preflight=json.loads')<activation.index("docker('tag',m['candidate_image']")
result={'passed':True,'active_research_blocks':True,'weekly_generation_blocks':True,'weekly_sending_blocks':True,'idle_passes':True,'active_final_report_blocks':True,'preflight_before_image_switch':True,'external_requests':0}
pathlib.Path(__file__).with_name('report-recovery-release-checks.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result))
