import pathlib,subprocess,json,base64
repo=pathlib.Path(__file__).resolve().parent.parent
script=(repo/'validation/campus_v3_backend_case.py').read_bytes()
command=['sudo','-n','docker','run','--rm','-i','--network','none','--entrypoint','python','bettafish:candidate-campus-polish-20261020','-']
import shlex
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(command)],input=script,capture_output=True,timeout=100)
if r.returncode:print(r.stderr.decode(errors='replace')[-2500:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
long_pdf=base64.b64decode(data.pop('long_pdf_base64'));pdf=base64.b64decode(data.pop('pdf_base64'));out=repo.parent/'validation-artifacts/campus-v3';out.mkdir(exist_ok=True)
(out/'fixture-flow.pdf').write_bytes(pdf)
from pypdf import PdfReader
reader=PdfReader(out/'fixture-flow.pdf');assert len(reader.pages)>=1
import unicodedata
assert '材料显示' in unicodedata.normalize('NFKC',''.join(p.extract_text() for p in reader.pages))
(out/'fixture-long-flow.pdf').write_bytes(long_pdf);long_reader=PdfReader(out/'fixture-long-flow.pdf');assert len(long_reader.pages)>4;assert '报告正文末尾验证标记' in unicodedata.normalize('NFKC',''.join(p.extract_text() for p in long_reader.pages)).replace('\n','');data['long_pdf_pages']=len(long_reader.pages);data['pdf_pages']=len(reader.pages);data['pdf_chinese_text_extractable']=True
(repo/'validation/campus-v3-backend-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
