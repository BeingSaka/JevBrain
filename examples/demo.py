"""Offline HTTP contract demo. Fixtures exercise wiring, not Jev accuracy."""
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_engine import answer, PROFILE, THRESHOLDS
from jev_engine.engine import Engine
from jev_engine.jev_client import JevClient, post_json
from jev_engine.worker import CommandWorker
from jev_engine.logging import JsonlLogger
calls=[]
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert set(payload['questions'])==set(PROFILE['questions'])
        calls.append(payload)
        good='Price has not been announced.' in payload['state']['candidate_output']
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps(answer(good)).encode())
    def log_message(*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
real_post=post_json
try:
    def fixture_post(url,payload,key=None,timeout=30,attempts=1):
        assert url=='https://api.typesafe.ai/v1/systemone'
        return real_post(f'http://127.0.0.1:{server.server_port}',payload,key,timeout,attempts)
    worker=CommandWorker([sys.executable,str(ROOT/'examples/fixture_worker.py')])
    with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'TYPESAFE_API_KEY':'OFFLINE-FIXTURE-KEY'}),patch('jev_engine.jev_client.post_json',side_effect=fixture_post):
        e=JevClient();e.name='fixture-http-not-live-jev'
        result=Engine(e,worker,PROFILE,THRESHOLDS,JsonlLogger(Path(tmp)/'events.jsonl')).run(json.loads((ROOT/'examples/input.json').read_text()))
        assert result['decision']=='PASS' and result['repairs']==1 and len(calls)==2
        summary={'mode':'OFFLINE FIXTURES — no live Jev or AI generation',
            'route':[x['policy_decision'] for x in result['history']], 'repairs':result['repairs'],
            'http_evaluations':len(calls),'final_output':result['final_output'],'result':'PASS'}
        print(json.dumps(summary,indent=2))
finally:server.shutdown();server.server_close();thread.join()
