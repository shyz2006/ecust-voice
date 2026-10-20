"""Mock the Resend HTTP transport; exercise request identification and safe diagnostics."""
import ast,pathlib,json,io,urllib.request,urllib.error
repo=pathlib.Path(__file__).resolve().parents[1]
tree=ast.parse((repo/'production/CampusPulse/weekly.py').read_text(encoding='utf-8'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='resend')
ns={'json':json,'Request':urllib.request.Request,'HTTPError':urllib.error.HTTPError,'URLError':urllib.error.URLError}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'resend','exec'),ns);calls=[]
def success(req,timeout):calls.append(req);return io.StringIO('{"id":"mock-mail-id"}')
ns['urlopen']=success
assert ns['resend']({'subject':'test'},'stable-id','re_fake_key')=='mock-mail-id'
assert calls[0].get_header('User-agent')=='ECUST-CampusWeekly/1.0'
assert calls[0].get_header('Accept')=='application/json'
assert calls[0].get_header('Idempotency-key')=='stable-id'
for code,body,expected in [(403,{'name':'invalid_permission','message':'re_fake_key'},'API Key'),(403,{'name':'suspended_api_key'},'Resend'),(401,{},'API Key'),(429,{'name':'monthly_quota_exceeded'},'Resend'),(403,{},'Logs')]:
 def fail(req,timeout):raise urllib.error.HTTPError(req.full_url,code,'error',{},io.BytesIO(json.dumps(body).encode()))
 ns['urlopen']=fail
 try:ns['resend']({},'stable-id','re_fake_key')
 except ValueError as exc:assert expected in str(exc) and 're_fake_key' not in str(exc)
 else:raise AssertionError('HTTP error not surfaced')
result={'passed':True,'explicit_user_agent':True,'accept_json':True,'safe_error_categories':5,'emails_sent':0}
(repo/'validation/resend-client-test-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
