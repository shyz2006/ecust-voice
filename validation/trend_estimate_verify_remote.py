import json,hashlib,urllib.request
expected={'static/js/campus-review.js': '5d806011e573a809bcfec5cdca3f8ec8ee9051dc2aa9bc3ef67683f663b8af15', 'static/css/campus-play.css': '6b4296032cc3db15200ff8f4825419cff998551973afb94648e864203c3cc3b5'}
checks=[]
for path,expected_hash in expected.items():
 with urllib.request.urlopen("http://127.0.0.1:5000/"+path+"?v=20261026t1",timeout=20) as r:data=r.read();status=r.status
 actual=hashlib.sha256(data).hexdigest()
 assert status==200 and actual==expected_hash
 checks.append({"path":path,"http":status,"sha256":actual,"matches_local":True})
print(json.dumps({"passed":True,"version":"20261026t1","checks":checks}))
