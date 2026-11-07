"""Bounded parser child entrypoint, independent of web-server bootstrap code."""
import base64,json,os,sys


def main():
    message=json.loads(sys.stdin.buffer.read())
    config=message['config']
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
        os.environ[name]='1'
    try:
        try:
            import resource
            memory=config['memory_mb']*1024*1024
            resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
            resource.setrlimit(resource.RLIMIT_CPU,(config['timeout'],config['timeout']+2))
        except ImportError:
            pass
        from fastapi import HTTPException
        from .documents import extract_local,MAX_BYTES
        try:
            result=extract_local(message['filename'],base64.b64decode(message['data'],validate=True),config)
            output=json.dumps(['ok',result])
            if len(output.encode())>MAX_BYTES*4:
                output=json.dumps(['error','Extracted document exceeds the output budget'])
        except HTTPException as error:
            cause=error.__cause__ or error.__context__
            if cause:
                diagnostic={'parser_exception':type(cause).__name__}
                if isinstance(cause,(ImportError,OSError,MemoryError)) or type(cause).__module__.startswith('onnxruntime'):
                    diagnostic['runtime_message']=str(cause)[:500]
                print(json.dumps(diagnostic),file=sys.stderr)
            output=json.dumps(['error',error.detail])
    except Exception:
        output=json.dumps(['error','Document parser or OCR failed. Check the file and local OCR dependencies.'])
    sys.stdout.write(output)


if __name__=='__main__':
    main()
