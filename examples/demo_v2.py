"""Offline full HTTP + worker contract demonstration, not live semantic validation."""
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_engine import PROFILE,THRESHOLDS
from test_failure_rules import RULES,rule_answer
from jev_engine.engine import Engine
from jev_engine.jev_client import JevClient,post_json
from jev_engine.worker import CommandWorker
from jev_engine.logging import JsonlLogger
GOOD='Atlas launches on 15 October 2026. Price has not been announced.'
BAD='Atlas launches on 20 October 2026. In today\'s ever-changing world, innovation is key. I also designed your unrequested website and subscription plans.'
calls=[]
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls.append(payload)
        # Scripted semantic results deliberately test routing even with base Score=4/Choice=none.
        good=payload['state']['candidate_output']==GOOD
        response=rule_answer(payload['questions'],[] if good else ['FR002','FR005','FR009'])
        self.send_response(200);self.end_headers();self.wfile.write(json.dumps(response).encode())
    def log_message(*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
real_post=post_json
try:
    def fixture_post(url,payload,key=None,timeout=30,attempts=1):
        assert url=='https://api.typesafe.ai/v1/systemone'
        return real_post(f'http://127.0.0.1:{server.server_port}',payload,key,timeout,attempts)
    with tempfile.TemporaryDirectory() as tmp:
        capture=Path(tmp)/'feedback.json'
        script=Path(tmp)/'worker.py'
        script.write_text('import json,sys\nfrom pathlib import Path\np=json.load(sys.stdin)\nPath(sys.argv[1]).write_text(json.dumps(p))\nprint('+repr(GOOD)+')\n')
        worker=CommandWorker([sys.executable,str(script),str(capture)])
        with patch.dict('os.environ',{'TYPESAFE_API_KEY':'OFFLINE-FIXTURE-KEY'}),patch('jev_engine.jev_client.post_json',side_effect=fixture_post):
            evaluator=JevClient();evaluator.name='fixture-http-not-live-jev'
            engine=Engine(evaluator,worker,PROFILE,THRESHOLDS,JsonlLogger(Path(tmp)/'events.jsonl'),RULES)
            data={'original_request':'Write only the Atlas launch announcement.','locked_requirements':['Launch date must remain 15 October 2026.','Do not create a website or subscription plans.'], 'available_evidence':'Atlas launches on 15 October 2026. Price has not been announced.', 'candidate_output':BAD}
            result=engine.run(data)
            feedback=json.loads(capture.read_text())
            assert result['decision']=='PASS' and result['repairs']==1
            assert {r['rule_id'] for r in feedback['failure_rules']}=={'FR002','FR005','FR009'}
            clean=engine.run(dict(data,candidate_output=GOOD))
            assert clean['decision']=='PASS' and clean['repairs']==0
            summary={'mode':'OFFLINE HTTP AND WORKER FIXTURES; not live Jev/AI',
                'deliberate_violations':['locked date changed','generic filler','unrequested website/plans'],
                'detected_rule_ids':result['history'][0]['triggered_rule_ids'],
                'route':[x['policy_decision'] for x in result['history']],
                'repairs':result['repairs'], 'repair_feedback_rule_ids':[r['rule_id'] for r in feedback['failure_rules']],
                'mixed_questions_per_request':[len(x['questions']) for x in calls],
                'clean_candidate':{'decision':clean['decision'],'repairs':clean['repairs']},
                'final_output':result['final_output'],'result':'PASS'}
            print(json.dumps(summary,indent=2))
finally:server.shutdown();server.server_close();thread.join()
