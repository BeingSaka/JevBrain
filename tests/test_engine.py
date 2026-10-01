import copy
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from jev_engine.engine import Engine
from jev_engine.jev_client import JevClient, post_json, validate_response
from jev_engine.logging import JsonlLogger
from jev_engine.normalize import EngineError, normalize
from jev_engine.policy import decide, validate_thresholds
from jev_engine.worker import CommandWorker, OllamaWorker
PROFILE = json.loads((ROOT/'evaluators/universal.json').read_text())
THRESHOLDS = json.loads((ROOT/'config/thresholds.json').read_text())
INPUT = json.loads((ROOT/'examples/input.json').read_text())

def answer(good=True):
    a = {}
    for k,q in PROFILE['questions'].items():
        if q['type'] == 'noul':
            positive = k in ('requirements_met','evidence_sufficient','ready_to_deliver')
            a[k] = {'type':'noul','noul': .99 if positive else .01}
    if not good:
        a['requirements_met']['noul'] = .01
        a['unsupported_claim_present']['noul'] = .99
        a['ready_to_deliver']['noul'] = .01
    choice = 'none' if good else 'unsupported_claim'
    a['primary_failure'] = {'type':'choice','choice':choice,'confidence':.99,
        'probabilities':{k:float(k==choice) for k in PROFILE['questions']['primary_failure']['criteria']}}
    score = 4 if good else 1
    a['production_readiness'] = {'type':'score','score':score,'confidence':.99,
        'probabilities':{str(i):float(i==score) for i in range(5)},
        'legend':{str(i):v for i,v in enumerate(PROFILE['questions']['production_readiness']['criteria'])}}
    return {'model':'jev-1.13.0','answers':a,'usage':{'input_tokens':1000,'output_tokens':50}}

class Evaluator:
    name = 'fixture-not-live-jev'
    def __init__(self, responses): self.responses, self.calls = list(responses), 0
    def evaluate(self,state,questions):
        self.calls += 1
        value = self.responses.pop(0)
        if isinstance(value, Exception): raise value
        return copy.deepcopy(value)

class Worker:
    name = 'fixture-not-ai'
    def __init__(self, outputs): self.outputs, self.payloads = list(outputs), []
    def run(self,payload): self.payloads.append(payload); return self.outputs.pop(0)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = JsonlLogger(Path(self.tmp.name)/'events.jsonl')
    def engine(self,e,w=None): return Engine(e,w,PROFILE,THRESHOLDS,self.log)
    def test_pass(self): self.assertEqual(self.engine(Evaluator([answer()])).run(INPUT)['decision'],'PASS')
    def test_repair_pass(self):
        e,w=Evaluator([answer(False),answer()]),Worker(['Atlas launches on 15 October 2026. Price has not been announced.'])
        r=self.engine(e,w).run(INPUT)
        self.assertEqual((r['decision'],r['repairs'],e.calls),('PASS',1,2))
        self.assertEqual(w.payloads[0]['primary_failure'],'unsupported_claim')
        self.assertIn('available_evidence',w.payloads[0]['required_correction'])
        self.assertEqual(len(self.log.path.read_text().splitlines()),2)
    def test_two_repairs_max(self):
        e,w=Evaluator([answer(False)]*3),Worker(['bad revision 1','bad revision 2'])
        r=self.engine(e,w).run(INPUT)
        self.assertEqual((r['decision'],r['repairs'],e.calls,len(w.payloads)),('HUMAN REVIEW',2,3,2))
    def test_unchanged_no_extra_call(self):
        e=Evaluator([answer(False)])
        r=self.engine(e,Worker([INPUT['candidate_output']])).run(INPUT)
        self.assertEqual((r['decision'],e.calls),('HUMAN REVIEW',1))
    def test_oscillation_stops(self):
        e=Evaluator([answer(False)]*2)
        r=self.engine(e,Worker(['second',INPUT['candidate_output']])).run(INPUT)
        self.assertEqual((r['decision'],e.calls),('HUMAN REVIEW',2))
    def test_uncertainty(self):
        r=answer();r['answers']['requirements_met']['noul']=.6
        self.assertEqual(decide(r,THRESHOLDS)[0],'HUMAN REVIEW')
    def test_hard_failure_overrides_score(self):
        r=answer(False);r['answers']['production_readiness']=answer()['answers']['production_readiness']
        self.assertEqual(decide(r,THRESHOLDS)[0],'REVISE')
    def test_low_confidence(self):
        r=answer();r['answers']['primary_failure']['confidence']=.2
        self.assertEqual(decide(r,THRESHOLDS)[0],'HUMAN REVIEW')
    def test_missing_evidence_no_repair(self):
        r=answer(False);r['answers']['evidence_sufficient']['noul']=.01
        w=Worker([])
        self.assertEqual(self.engine(Evaluator([r]),w).run(INPUT)['decision'],'HUMAN REVIEW')
        self.assertEqual(w.payloads,[])
    def test_deterministic_skips_jev(self):
        data=copy.deepcopy(INPUT);data['deterministic_checks']={'valid_json':True}
        e=Evaluator([answer()]);w=Worker(['{"message":"Atlas"}'])
        result=self.engine(e,w).run(data)
        self.assertEqual((result['decision'],e.calls),('PASS',1))
        self.assertIsNone(result['history'][0]['jev_results'])
    def test_initial_generation(self):
        data=copy.deepcopy(INPUT);data.pop('candidate_output')
        w=Worker(['Atlas launches on 15 October 2026.'])
        self.assertEqual(self.engine(Evaluator([answer()]),w).run(data)['decision'],'PASS')
        self.assertEqual(len(w.payloads),1)
    def test_no_worker_review(self):
        self.assertEqual(self.engine(Evaluator([answer(False)])).run(INPUT)['decision'],'HUMAN REVIEW')
    def test_provider_error_review(self):
        r=self.engine(Evaluator([EngineError('Provider HTTP 401')])).run(INPUT)
        self.assertEqual(r['decision'],'HUMAN REVIEW')
        self.assertEqual(r['history'][0]['reason'],'Provider HTTP 401')
    def test_malformed_response_review(self):
        r=answer();r['answers']['requirements_met']['noul']=float('nan')
        self.assertEqual(self.engine(Evaluator([r])).run(INPUT)['decision'],'HUMAN REVIEW')
    def test_distribution_validation(self):
        r=answer();r['answers']['primary_failure']['probabilities']['none']=.5
        with self.assertRaises(EngineError):validate_response(r,PROFILE['questions'])
    def test_input_validation(self):
        with self.assertRaises(EngineError):normalize({'original_request':'x','locked_requirements':'wrong'})
        with self.assertRaises(EngineError):normalize({'original_request':'x','unknown':'x'})
    def test_bad_threshold(self):
        t=dict(THRESHOLDS,risk_max=.9)
        with self.assertRaises(EngineError):validate_thresholds(t)
    def test_missing_key_no_network(self):
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':''}):
            with self.assertRaises(EngineError):JevClient().evaluate(INPUT,PROFILE['questions'])
    def test_context_guard(self):
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':'fixture-key'}),patch('jev_engine.jev_client.post_json') as post:
            with self.assertRaises(EngineError):JevClient().evaluate({'text':'x'*31000},PROFILE['questions'])
            post.assert_not_called()
    def test_command_worker(self):
        w=CommandWorker([sys.executable,'-c','import sys,json; x=json.load(sys.stdin); print(x["original_request"])'])
        self.assertEqual(w.run({'original_request':'abc'}),'abc')
    def test_http_retry_and_auth(self):
        headers=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(s):
                headers.append(s.headers.get('Authorization'))
                s.rfile.read(int(s.headers['Content-Length']))
                s.send_response(429 if len(headers)==1 else 200)
                s.send_header('Retry-After','0');s.end_headers()
                s.wfile.write(json.dumps(answer()).encode())
            def log_message(*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            r=post_json(f'http://127.0.0.1:{server.server_port}',{},'fixture-key',attempts=2)
            self.assertEqual(r['model'],'jev-1.13.0')
            self.assertEqual(headers,['Bearer fixture-key']*2)
        finally:server.shutdown();server.server_close();thread.join()
    def test_redirect_no_key_forwarding(self):
        err=urllib.error.HTTPError('https://api.typesafe.ai',302,'redirect',{},io.BytesIO())
        with patch('urllib.request.OpenerDirector.open',side_effect=err):
            with self.assertRaisesRegex(EngineError,'HTTP 302'):post_json('https://api.typesafe.ai',{},'secret')
    def test_ollama_local_only(self):
        with patch.dict(os.environ,{'OLLAMA_MODEL':'existing','OLLAMA_URL':'https://external.example'}):
            with self.assertRaises(EngineError):OllamaWorker()
    def test_worker_failure_stops(self):
        class FailedWorker:
            name = "failed-fixture"
            def run(self,payload): raise EngineError("Worker launch/timeout failure")
        r=self.engine(Evaluator([answer(False)]),FailedWorker()).run(INPUT)
        self.assertEqual((r['decision'],r['repairs']),('HUMAN REVIEW',1))
    def test_ollama_http_adapter(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(s):
                captured.append(json.loads(s.rfile.read(int(s.headers['Content-Length']))))
                s.send_response(200);s.end_headers()
                s.wfile.write(json.dumps({'response':'local fixture response','done':True}).encode())
            def log_message(*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.dict(os.environ,{'OLLAMA_MODEL':'fixture','OLLAMA_URL':f'http://127.0.0.1:{server.server_port}'}):
                self.assertEqual(OllamaWorker().run({'original_request':'task'}),'local fixture response')
            self.assertIs(captured[0]['stream'],False)
            self.assertEqual(captured[0]['model'],'fixture')
        finally:server.shutdown();server.server_close();thread.join()
    def test_log_has_hashes_not_content(self):
        r=self.engine(Evaluator([answer()])).run(INPUT)
        text=self.log.path.read_text()
        self.assertNotIn(INPUT['candidate_output'],text)
        self.assertIn('state_sha256',text)

if __name__=='__main__':unittest.main()
