import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_engine import ROOT,PROFILE,THRESHOLDS,INPUT
from test_failure_rules import RULES,RuleEvaluator
from jev_engine.engine import Engine
from jev_engine.logging import JsonlLogger
from jev_engine.worker import AIWorker,OllamaWorker,configured_worker,REPAIR_RULE

class OperationWorker(AIWorker):
    name='operation-fixture-not-ai'
    def __init__(self,outputs):self.outputs=list(outputs);self.calls=[]
    def run(self,payload):
        self.calls.append(copy.deepcopy(payload))
        self.last_usage={'prompt_eval_count':50,'eval_count':20}
        return self.outputs.pop(0)

class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    def engine(self,e,w):return Engine(e,w,PROFILE,THRESHOLDS,JsonlLogger(Path(self.tmp.name)/'events.jsonl'),RULES)
    def test_case1_clean_zero_repairs(self):
        w=OperationWorker([])
        r=self.engine(RuleEvaluator([{}]),w).run(INPUT)
        self.assertEqual((r['decision'],w.calls,r['worker_calls']),('PASS',[],[]))
    def test_case2_repair_targeted_pass(self):
        w=OperationWorker(['corrected candidate'])
        class RepairableEvaluator(RuleEvaluator):
            def evaluate(self,state,questions):
                response=super().evaluate(state,questions)
                if response['answers']['unsupported_claim_present']['noul']>.8:
                    c=response['answers']['primary_failure'];c['choice']='unsupported_claim'
                    c['probabilities']={k:float(k=='unsupported_claim') for k in c['probabilities']}
                return response
        r=self.engine(RepairableEvaluator([{'violations':['FR003']},{}]),w).run(INPUT)
        self.assertEqual((r['decision'],r['repairs']),('PASS',1))
        payload=w.calls[0]
        self.assertEqual(payload['operation'],'repair')
        self.assertEqual(payload['failure_rules'][0]['rule_id'],'FR003')
        self.assertIn('invent no facts',payload['failure_rules'][0]['repair_instruction'])
        self.assertIn(REPAIR_RULE,payload['required_correction']['rule'])
        self.assertNotIn('history',payload)
        self.assertEqual(r['worker_calls'][0]['usage']['eval_count'],20)
    def test_case3_human_review_worker_not_called(self):
        w=OperationWorker([])
        r=self.engine(RuleEvaluator([{'overrides':{'failure_FR009':.4}}]),w).run(INPUT)
        self.assertEqual((r['decision'],w.calls),('HUMAN REVIEW',[]))
    def test_case4_two_repairs_no_third(self):
        w=OperationWorker(['still bad 1','still bad 2'])
        r=self.engine(RuleEvaluator([{'violations':['FR009']}]*3),w).run(INPUT)
        self.assertEqual((r['decision'],r['repairs'],len(w.calls)),('HUMAN REVIEW',2,2))
        self.assertTrue(all(p['operation']=='repair' for p in w.calls))
    def test_case5_preserve_correct_section(self):
        data=dict(INPUT,candidate_output='KEEP: Atlas.\nDATE: wrong.')
        class PreserveWorker(AIWorker):
            name='preservation-fixture'
            def run(self,payload):
                assert payload['operation']=='repair'
                assert payload['failure_rules'][0]['rule_id']=='FR002'
                return payload['previous_candidate'].replace('DATE: wrong.','DATE: 15 October 2026.')
        r=self.engine(RuleEvaluator([{'violations':['FR002']},{}]),PreserveWorker()).run(data)
        self.assertEqual(r['decision'],'PASS')
        self.assertEqual(r['final_output'].splitlines()[0],data['candidate_output'].splitlines()[0])
    def test_generate_then_evaluate(self):
        data=copy.deepcopy(INPUT);data.pop('candidate_output');data['known_constraints']=['Be concise']
        w=OperationWorker(['generated candidate'])
        r=self.engine(RuleEvaluator([{}]),w).run(data)
        self.assertEqual(r['decision'],'PASS')
        self.assertEqual(w.calls[0]['operation'],'generate')
        self.assertEqual(w.calls[0]['known_constraints'],['Be concise'])
        self.assertNotIn('history',w.calls[0])
    def test_ollama_repair_system_and_usage(self):
        with patch.dict(os.environ,{'OLLAMA_MODEL':'installed-local-model','OLLAMA_URL':'http://localhost:11434'}):
            w=OllamaWorker()
        with patch('jev_engine.worker.post_json',return_value={'done':True,'response':'corrected','prompt_eval_count':10,'eval_count':5,'total_duration':100}) as post:
            self.assertEqual(w.repair({'previous_candidate':'before','required_correction':{'rule':REPAIR_RULE}}),'corrected')
            self.assertIn(REPAIR_RULE,post.call_args.args[1]['system'])
            self.assertEqual(w.last_usage['prompt_eval_count'],10)
    def test_configuration_missing_explains_none(self):
        with patch.dict(os.environ,{'OLLAMA_MODEL':'','WORKER_COMMAND_JSON':''}):self.assertIsNone(configured_worker())
    def test_unchanged_worker_no_extra_jev(self):
        w=OperationWorker([INPUT['candidate_output']]);e=RuleEvaluator([{'violations':['FR009']}])
        r=self.engine(e,w).run(INPUT)
        self.assertEqual((r['decision'],len(e.calls),len(w.calls)),('HUMAN REVIEW',1,1))

if __name__=='__main__':unittest.main()
