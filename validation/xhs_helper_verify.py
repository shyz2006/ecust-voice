import hashlib,json,urllib.request
from pathlib import Path
p=Path('/app/static/downloads/ecust-xhs-browser-helper.zip')
with urllib.request.urlopen('http://127.0.0.1:5000/static/downloads/ecust-xhs-browser-helper.zip',timeout=10) as response:
 data=response.read();assert response.status==200
assert hashlib.sha256(data).hexdigest()==hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'helper_zip_verified':True,'sha256':hashlib.sha256(data).hexdigest(),'notes_uploaded':0,'emails_sent':0}))
