"""Exercise the actual mandatory preflight extracted from the activation script."""
import ast,json,pathlib,re,sys,types
from unittest.mock import patch
source=pathlib.Path(__file__).with_name('workshop_choices_release.py').read_text(encoding='utf-8')
activation=re.findall(r"script=r\'\'\'(.*?)\'\'\'",source,re.S)[-1]
node=next(n for n in ast.walk(ast.parse(activation)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='guard_code' for t in n.targets))
code=ast.literal_eval(node.value)
active=[];weeklies=[]
weekly=types.SimpleNamespace(config=lambda full:{'api_key':'fake-unit-key'},recent=lambda:weeklies)
modules={'CampusPulse':types.SimpleNamespace(weekly=weekly),'utils.research_runner':types.SimpleNamespace(active_research_tasks=lambda:active)}
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
assert activation.index('preflight=json.loads')<activation.index("docker('tag',m['candidate_image']")
result={'passed':True,'active_research_blocks':True,'weekly_generation_blocks':True,'weekly_sending_blocks':True,'idle_passes':True,'preflight_before_image_switch':True,'external_requests':0}
pathlib.Path(__file__).with_name('workshop-choices-release-checks.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result))
