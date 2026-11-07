"""Disposable Compose integration stack. No credentials are printed or persisted."""
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compose-executable')
    parser.add_argument('--config-only',action='store_true')
    args=parser.parse_args()
    project='loanwise-test-'+secrets.token_hex(5)
    command=([args.compose_executable] if args.compose_executable else ['docker','compose'])+['-p',project,'-f',str(ROOT/'docker-compose.yml')]
    env={**os.environ,'POSTGRES_PASSWORD':secrets.token_hex(24),'DEMO_MODE':'true','COOKIE_SECURE':'false','OCR_ENABLED':'true','ALLOWED_ORIGIN':'http://localhost:8080'}
    report={'project':project,'configuration_valid':False,'engine_available':False,'runtime_verified':False}
    directory=ROOT/'runtime'/'verification';directory.mkdir(parents=True,exist_ok=True)
    attempted=False

    def execute(*arguments,timeout=120):
        return subprocess.run(command+list(arguments),cwd=ROOT,env=env,capture_output=True,text=True,timeout=timeout)

    def require(result,message):
        if result.returncode:
            detail=(result.stderr or result.stdout)[-2500:].replace(env['POSTGRES_PASSWORD'],'[redacted]')
            raise RuntimeError(message+': '+detail)
        return result.stdout

    try:
        require(execute('config','--quiet'),'Compose configuration failed')
        report['configuration_valid']=True
        engine=execute('ps','--format','json')
        if engine.returncode:
            report['blocker']='Docker engine is unavailable: '+engine.stderr.strip()[-1000:]
            print(report['blocker'])
            return 2
        report['engine_available']=True
        if args.config_only:
            return 0
        attempted=True
        print('Building and starting the isolated Compose test stack.',flush=True)
        require(execute('up','--build','-d','--wait','--wait-timeout','240',timeout=1500),'Compose build/start failed')
        require(execute('exec','-T','backend','python','-m','ml.pipeline',timeout=300),'Container ML training failed')
        require(execute('restart','backend'),'Backend restart failed')
        import httpx
        with httpx.Client(base_url='http://127.0.0.1:8080',timeout=120) as client:
            deadline=time.monotonic()+90
            while True:
                try:
                    health=client.get('/api/health').json()
                    if health['status']=='ok' and health['model_ready']:
                        break
                except (httpx.HTTPError,ValueError,KeyError):
                    pass
                if time.monotonic()>deadline:
                    raise RuntimeError('Container backend did not become healthy with the trained model')
                time.sleep(1)
            credentials=require(execute('exec','-T','backend','cat','runtime/demo-credentials.txt'),'Cannot read generated test credentials').splitlines()
            login=client.post('/api/auth/login',json={'email':credentials[0].removeprefix('Email: '),'password':credentials[1].removeprefix('Password: ')})
            login.raise_for_status()
            applications=client.get('/api/applications').json()
            assert applications['total']==500
            assessment=client.post('/api/eligibility/assess',json={'application_id':2})
            assessment.raise_for_status();result=assessment.json()
            assert result['agent_count']==12 and result['risk']['contributions']
            assert result['eligibility']['overall_status'] not in ('APPROVED','REJECTED')
            evidence=client.post('/api/rag/query',json={'question':'minimum income requirements','product_id':1})
            evidence.raise_for_status();assert evidence.json()['citations']
            from PIL import Image,ImageDraw,ImageFont
            image=Image.new('RGB',(1500,300),'white')
            ImageDraw.Draw(image).text((60,80),'Monthly income: 50000',font=ImageFont.load_default(size=60),fill='black')
            buffer=io.BytesIO();image.save(buffer,format='PNG')
            document=client.post('/api/documents/upload',files={'file':('synthetic-scan.png',buffer.getvalue(),'image/png')},data={'application_id':2})
            document.raise_for_status()
            assert document.json()['pages'][0]['method']=='local_ocr'
            assert not document.json()['extraction']['verified']
            html=client.get('/');html.raise_for_status();assert 'id="root"' in html.text
            report.update(runtime_verified=True,applications=500,agents=12,ocr_verified=True,shap_verified=True,policy_citations_verified=True)
        print('Container integration passed: PostgreSQL, migrations, API, OCR, ML/SHAP, RAG and frontend.',flush=True)
        return 0
    except (RuntimeError,OSError,AssertionError,subprocess.TimeoutExpired) as error:
        report['error']=str(error).replace(env['POSTGRES_PASSWORD'],'[redacted]')
        print(report['error'],file=sys.stderr)
        return 1
    finally:
        if attempted:
            # Only the randomly named test project and its disposable volumes are removed.
            cleanup=execute('down','--volumes','--remove-orphans',timeout=120)
            report['cleanup_passed']=cleanup.returncode==0
        (directory/'docker.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':
    raise SystemExit(main())
