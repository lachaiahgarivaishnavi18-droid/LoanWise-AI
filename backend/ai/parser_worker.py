"""Spawn-based parser isolation with a hard wall timeout and Unix resource limits."""
import multiprocessing
import threading
import time
from app.config import settings
from fastapi import HTTPException

SLOTS=threading.BoundedSemaphore(2)


def worker(connection,filename,data,config):
    try:
        import os
        for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
            os.environ[name]='1'
        try:
            import resource
            memory=config['memory_mb']*1024*1024
            resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
            resource.setrlimit(resource.RLIMIT_CPU,(config['timeout'],config['timeout']+2))
        except ImportError:
            pass  # Windows still has process isolation, byte/pixel/page limits and a kill timeout.
        from .documents import extract_local
        result=extract_local(filename,data,config)
        connection.send(('ok',result))
    except HTTPException as error:
        connection.send(('error',error.detail))
    except Exception:
        connection.send(('error','Document parser or OCR failed. Check the file and local OCR dependencies.'))
    finally:
        connection.close()


def parse_isolated(filename,data,config):
    if not SLOTS.acquire(timeout=2):
        raise HTTPException(503,'Document parser capacity is busy; try again shortly')
    if settings.parser_process_mode=='subprocess':
        try:
            return parse_subprocess(filename,data,config)
        finally:
            SLOTS.release()
    context=multiprocessing.get_context('spawn')
    parent,child=context.Pipe(duplex=False)
    process=context.Process(target=worker,args=(child,filename,data,config),daemon=True)
    try:
        process.start();child.close()
        import psutil
        monitored=psutil.Process(process.pid)
        deadline=time.monotonic()+config['timeout']
        while not parent.poll(.1):
            if time.monotonic()>=deadline:
                raise HTTPException(422,'Document parsing exceeded the configured timeout; no extraction was accepted')
            try:
                if monitored.memory_info().rss>config['memory_mb']*1024*1024:
                    raise HTTPException(422,'Document parser exceeded the configured memory budget')
            except psutil.NoSuchProcess:
                raise HTTPException(422,'Document parser exited before producing an extraction')
        try:
            status,result=parent.recv()
        except EOFError:
            raise HTTPException(422,'Document parser exited without a usable extraction')
        if status!='ok':
            raise HTTPException(422,result)
        return result
    finally:
        if process.pid and process.is_alive():
            process.terminate()
        if process.pid:
            process.join(timeout=2)
            if process.is_alive():
                process.kill();process.join(timeout=2)
        parent.close();child.close();SLOTS.release()


def parse_subprocess(filename,data,config):
    """Use a dedicated module instead of re-executing a serverless host's __main__."""
    import base64,json,os,subprocess,sys,psutil
    environment=os.environ.copy()
    environment['PYTHONPATH']=os.pathsep.join(str(path) for path in sys.path if path)
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
        environment[name]='1'
    payload=json.dumps({'filename':filename,'data':base64.b64encode(data).decode(),'config':config}).encode()
    process=subprocess.Popen([sys.executable,'-m','ai.parser_cli'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment)
    monitored=psutil.Process(process.pid)
    deadline=time.monotonic()+config['timeout']
    pending=payload
    try:
        while True:
            try:
                output,diagnostic=process.communicate(input=pending,timeout=.1)
                break
            except subprocess.TimeoutExpired:
                pending=None
                if time.monotonic()>=deadline:
                    raise HTTPException(422,'Document parsing exceeded the configured timeout; no extraction was accepted')
                try:
                    if monitored.memory_info().rss>config['memory_mb']*1024*1024:
                        raise HTTPException(422,'Document parser exceeded the configured memory budget')
                except psutil.NoSuchProcess:
                    pass
        if process.returncode or not output:
            raise HTTPException(422,'Document parser exited without a usable extraction')
        status,result=json.loads(output)
        if status!='ok':
            if diagnostic:
                import logging
                logging.getLogger(__name__).warning('Parser runtime diagnostic: %s',diagnostic.decode(errors='replace')[:1000])
            raise HTTPException(422,result)
        return result
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
