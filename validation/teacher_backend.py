import pathlib,subprocess,json,base64
repo=pathlib.Path(__file__).resolve().parent.parent
script=(repo/'validation/teacher_backend_case.py').read_bytes()
command=['sudo','-n','docker','run','--rm','-i','--network','none','--entrypoint','python','bettafish:candidate-teacher-feedback-20261020','-']
import shlex
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(command)],input=script,capture_output=True,timeout=100)
if r.returncode:print(r.stderr.decode(errors='replace')[-2500:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
pdf=base64.b64decode(data.pop('pdf_base64'));out=repo.parent/'validation-artifacts/teacher';out.mkdir(exist_ok=True)
(out/'fixture-four-pages.pdf').write_bytes(pdf)
from pypdf import PdfReader
reader=PdfReader(out/'fixture-four-pages.pdf');assert len(reader.pages)==4
import unicodedata
assert all('材料显示' in unicodedata.normalize('NFKC',p.extract_text()) for p in reader.pages)
data['pdf_pages']=4;data['pdf_chinese_text_extractable']=True
(repo/'validation/teacher-backend-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
