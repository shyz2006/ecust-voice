import json,hashlib,urllib.request
expected={'static/js/campus-review.js': '2843773df5371bf0910adaac899832fa6cdfab36951b29f31cd0421ed9dacb10', 'static/css/campus-play.css': '2eb191b4ef515e343b41de7d921f4ec594aa30ff51d6f186e6de5f2d67fde9d5'}
checks=[]
for path,expected_hash in expected.items():
 with urllib.request.urlopen("http://127.0.0.1:5000/"+path+"?v=20261025t2",timeout=20) as r:data=r.read();status=r.status
 actual=hashlib.sha256(data).hexdigest()
 assert status==200 and actual==expected_hash
 checks.append({"path":path,"http":status,"sha256":actual,"matches_local":True})
print(json.dumps({"passed":True,"version":"20261025t2","checks":checks}))
