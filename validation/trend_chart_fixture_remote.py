import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:5000/pulse/api/revision/overview',timeout=60) as r:d=json.load(r)
keys=('theme','color','posts','posts_24h','delta','comparison','reference','timeline')
print(json.dumps({'generated_at':d['generated_at'],'themes':[{k:t[k] for k in keys} for t in d['themes']]},ensure_ascii=True))
