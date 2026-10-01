import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from test_engine import ROOT,INPUT,answer,Evaluator
import test_worker_integration as wi
from jev_engine.worker import CommandWorker
sys.path.insert(0,str(ROOT))
import antigravity_worker as bridge

class AntigravityTests(unittest.TestCase):
    def test_generate_compact_whitelist(self):
        payload={'operation':'generate','original_request':'Write message','locked_requirements':['Keep name'],
                 'available_evidence':'facts','known_constraints':['short'],'output_type':'text',
                 'history':'UNRELATED_HISTORY','probabilities':{'x':1}}
        prompt=bridge.prompt_for(payload)
        data=json.loads(prompt.split('\n',1)[1])
        self.assertEqual(set(data),{'original_request','locked_requirements','available_evidence','known_constraints','output_type'})
        self.assertNotIn('UNRELATED_HISTORY',prompt)
    def test_repair_targeted_preservation(self):
        payload={'operation':'repair','previous_candidate':'correct A; wrong B','failed_dimensions':['rule:FR003','unsupported_claim_present'],
             'locked_requirements':['Preserve A'],'failure_rules':[{'rule_id':'FR003','probability':.99,'repair_instruction':'Remove invented B'}],
             'required_correction':{'actions':['Remove invented B'],'available_evidence':'B unknown'},'history':'DO_NOT_SEND'}
        prompt=bridge.prompt_for(payload)
        self.assertIn(bridge.REPAIR_RULE,prompt)
        self.assertNotIn('probability',prompt);self.assertNotIn('DO_NOT_SEND',prompt)
        data=json.loads(prompt.split('\n',1)[1])
        self.assertEqual(data['triggered_failure_rules'],[{'rule_id':'FR003','repair_instruction':'Remove invented B'}])
        self.assertEqual(data['repair_instructions'],[])
    def test_native_argv_and_candidate(self):
        with patch('antigravity_worker.shutil.which',return_value='/tools/agy'),patch.dict(os.environ,{'ANTIGRAVITY_MODEL':bridge.DEFAULT_MODEL}),patch('antigravity_worker.subprocess.run',return_value=subprocess.CompletedProcess([],0,'CANDIDATE\n','ignored')) as run:
            self.assertEqual(bridge.invoke('prompt'),'CANDIDATE')
            self.assertEqual(run.call_args.args[0],['/tools/agy','-p','prompt','--model',bridge.DEFAULT_MODEL])
            self.assertIs(run.call_args.kwargs['shell'],False)
    def test_missing_timeout_nonzero_empty(self):
        with patch('antigravity_worker.shutil.which',return_value=None):
            with self.assertRaises(bridge.BridgeError):bridge.invoke('x')
        for result in [subprocess.CompletedProcess([],1,'','SECRET'),subprocess.CompletedProcess([],0,'  ','SECRET')]:
            with patch('antigravity_worker.shutil.which',return_value='/agy'),patch('antigravity_worker.subprocess.run',return_value=result):
                with self.assertRaises(bridge.BridgeError) as e:bridge.invoke('x')
                self.assertNotIn('SECRET',str(e.exception))
        with patch('antigravity_worker.shutil.which',return_value='/agy'),patch('antigravity_worker.subprocess.run',side_effect=subprocess.TimeoutExpired('agy',90)):
            with self.assertRaises(bridge.BridgeError):bridge.invoke('x')
    def test_stdout_candidate_only(self):
        out,err=io.StringIO(),io.StringIO()
        with patch('sys.stdin',io.StringIO(json.dumps({'original_request':'task'}))),patch('sys.stdout',out),patch('sys.stderr',err),patch('antigravity_worker.invoke',return_value='candidate'):
            self.assertEqual(bridge.main(),0)
        self.assertEqual(out.getvalue(),'candidate\n');self.assertEqual(err.getvalue(),'')
    def test_malformed_input_no_candidate(self):
        for raw in ('not JSON','[]','{"operation":"unknown"}','{"original_request":4}'):
            out,err=io.StringIO(),io.StringIO()
            with patch('sys.stdin',io.StringIO(raw)),patch('sys.stdout',out),patch('sys.stderr',err),patch('antigravity_worker.invoke') as invoke:
                self.assertEqual(bridge.main(),1)
                invoke.assert_not_called()
            self.assertEqual(out.getvalue(),'')
    def test_real_bridge_failure_stops_engine(self):
        # Local subprocess only: empty executable ensures no real cloud call.
        with patch.dict(os.environ,{'ANTIGRAVITY_EXECUTABLE':'nonexistent-agy-fixture-executable'}):
            worker=CommandWorker([sys.executable,str(ROOT/'antigravity_worker.py')])
            helper=wi.WorkerIntegrationTests();helper.setUp()
            try:
                from test_failure_rules import RuleEvaluator
                r=helper.engine(RuleEvaluator([{'violations':['FR009']}]),worker).run(INPUT)
                self.assertEqual(r['decision'],'HUMAN REVIEW')
                self.assertEqual(r['worker_calls'][0]['status'],'error')
            finally:helper.tmp.cleanup()
    def test_exact_constraints_not_dropped(self):
        data=json.loads(bridge.prompt_for({'original_request':'task','deterministic_constraints':{'max_chars':20}}).split('\n',1)[1])
        self.assertIn('max_chars',data['known_constraints'][0])

if __name__=='__main__':unittest.main()
