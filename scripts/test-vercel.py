"""Verify the deployed synthetic Vercel/Neon workspace; never print credentials."""
import argparse,io,json,time
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFont

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='https://loanwise-ai-eta.vercel.app')
parser.add_argument('--credentials',default='runtime/cloud-bootstrap/demo-credentials.txt')
args=parser.parse_args()
values=Path(args.credentials).read_text().splitlines()
email=values[0].removeprefix('Email: ');password=values[1].removeprefix('Password: ')
report={'url':args.url,'passed':False,'synthetic_only':True}
started=time.monotonic()
with httpx.Client(base_url=args.url,timeout=240,headers={'Origin':args.url}) as client:
 def checked(method,path,**kwargs):
  request_started=time.monotonic()
  response=client.request(method,path,**kwargs)
  print(f'{method} {path}: {response.status_code} ({time.monotonic()-request_started:.1f}s)',flush=True)
  if not response.is_success:raise RuntimeError(f'{method} {path}: HTTP {response.status_code}: {response.text[:300]}')
  return response
 report['health']=checked('GET','/api/health').json()
 checked('POST','/api/auth/login',json={'email':email,'password':password})
 applications=checked('GET','/api/applications').json()
 assert applications['total']==500
 report['application_count']=applications['total']
 assessment=checked('POST','/api/eligibility/assess',json={'application_id':2}).json()
 report['assessment_keys']=list(assessment)
 assert assessment['agent_count']==12
 risk=assessment['risk'] if 'risk' in assessment else assessment['credit_risk']
 assert risk['score'] is not None and len(risk['contributions'])==5
 report['agents']=12;report['shap_contributions']=5
 rag=checked('POST','/api/rag/query',json={'question':'What is the minimum monthly income?','product_id':1}).json()
 assert rag['evidence'];report['policy_citations']=len(rag['evidence'])
 image=Image.new('RGB',(1500,450),'white');draw=ImageDraw.Draw(image)
 font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',52)
 for y,text in [(70,'SYNTHETIC CLOUD VERIFICATION'),(170,'Monthly income: 50000'),(270,'Monthly debt: 12000')]:draw.text((70,y),text,font=font,fill='black')
 buffer=io.BytesIO();image.save(buffer,format='PNG');source=buffer.getvalue()
 document=checked('POST','/api/documents/upload',files={'file':('synthetic-cloud-scan.png',source,'image/png')},data={'application_id':499}).json()
 assert document['pages'][0]['method']=='local_ocr'
 assert not document['extraction']['verified']
 report['ocr_document_id']=document['id'];report['ocr_method']=document['pages'][0]['method']
 assert checked('GET',f"/api/documents/{document['id']}/download").content==source
 report['persistent_original_verified']=True
 assert checked('GET','/applications/new').headers['content-type'].startswith('text/html')
 report['passed']=True;report['duration_seconds']=round(time.monotonic()-started,2)
 directory=Path('runtime/verification');directory.mkdir(parents=True,exist_ok=True)
 (directory/'vercel.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
