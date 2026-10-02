import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_engine import ROOT, PROFILE, THRESHOLDS, INPUT, answer, Worker, Evaluator
from jev_engine.engine import Engine
from jev_engine.failure_rules import load_packs, validate_rules, applicable, questions_for
from jev_engine.logging import JsonlLogger
from jev_engine.normalize import EngineError, normalize, deterministic

RULES=load_packs([ROOT/'rules/universal.json'],PROFILE)

def rule_answer(questions, violations=(), overrides=None):
    result=answer()
    for key,q in questions.items():
        if key.startswith('failure_'):
            rid=key.removeprefix('failure_')
            result['answers'][key]={'type':'noul','noul':.99 if rid in violations else .01}
    for rid in violations:
        r=next(r for r in RULES if r['rule_id']==rid)
        if r['detector']['kind']=='reuse':
            result['answers'][r['detector']['question_id']]['noul']=.99
    for k,v in (overrides or {}).items():result['answers'][k]['noul']=v
    return result

class RuleEvaluator:
    name='fixture-not-live-jev'
    def __init__(self,rounds):self.rounds=list(rounds);self.calls=[]
    def evaluate(self,state,questions):
        self.calls.append(copy.deepcopy({'state':state,'questions':questions}))
        args=self.rounds.pop(0)
        return rule_answer(questions,**args)

class RuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.logger=JsonlLogger(Path(self.tmp.name)/'events.jsonl')
    def engine(self,e,w=None,rules=None):return Engine(e,w,PROFILE,THRESHOLDS,self.logger,RULES if rules is None else rules)
    def test_starter_count_and_no_duplicate_nouls(self):
        self.assertEqual(len(RULES),10)
        state,_=normalize(INPUT)
        active=applicable(RULES,state)
        self.assertEqual(len(active),9)
        self.assertEqual(len(questions_for(PROFILE,active)),16)
        self.assertNotIn('failure_FR003',questions_for(PROFILE,active))
    def test_multiple_violations_targeted_repair_pass(self):
        e=RuleEvaluator([{'violations':['FR002','FR005','FR009']},{}])
        w=Worker(['Atlas launches on 15 October 2026.'])
        result=self.engine(e,w).run(INPUT)
        self.assertEqual([x['policy_decision'] for x in result['history']],['REVISE','PASS'])
        feedback=w.payloads[0]['failure_rules']
        self.assertEqual({r['rule_id'] for r in feedback},{'FR002','FR005','FR009'})
        self.assertTrue(all(r['repair_instruction'] for r in feedback))
        self.assertIn('failure_FR007',e.calls[1]['questions'])
        self.assertEqual(e.calls[1]['state']['previous_candidate'],INPUT['candidate_output'])
        self.assertTrue(result['history'][1]['repair_performed'])
        self.assertEqual(result['repairs'],1)
    def test_clean_no_rewrite(self):
        e=RuleEvaluator([{}]);w=Worker([])
        result=self.engine(e,w).run(INPUT)
        self.assertEqual((result['decision'],result['repairs'],w.payloads),('PASS',0,[]))
    def test_critical_blocks_perfect_score_and_none_choice(self):
        result=self.engine(RuleEvaluator([{'violations':['FR002']}])).run(INPUT)
        self.assertEqual(result['history'][0]['jev_results']['answers']['production_readiness']['score'],4)
        self.assertEqual(result['decision'],'HUMAN REVIEW') # Missing worker, but cannot PASS.
        self.assertIn('FR002',result['history'][0]['triggered_rule_ids'])
    def test_rule_uncertainty_review(self):
        result=self.engine(RuleEvaluator([{'overrides':{'failure_FR009':.4}}]),Worker([])).run(INPUT)
        self.assertEqual(result['decision'],'HUMAN REVIEW')
    def test_info_advisory_not_repaired(self):
        rules=copy.deepcopy(RULES);rules[4]['severity']='INFO'
        w=Worker([])
        result=self.engine(RuleEvaluator([{'violations':['FR005']}]),w,rules).run(INPUT)
        self.assertEqual((result['decision'],w.payloads),('PASS',[]))
        finding=next(x for x in result['history'][0]['rule_findings'] if x['rule_id']=='FR005')
        self.assertEqual(finding['policy_impact'],'advisory')
    def test_disabled_and_task_scoped(self):
        rules=copy.deepcopy(RULES)
        rules[4]['enabled']=False;rules[8]['applicable_types']=['research']
        e=RuleEvaluator([{}]);self.engine(e,rules=rules).run(INPUT)
        self.assertNotIn('failure_FR005',e.calls[0]['questions'])
        self.assertNotIn('failure_FR009',e.calls[0]['questions'])
    def test_recurrence_logged_and_cap(self):
        e=RuleEvaluator([{'violations':['FR009']}]*3);w=Worker(['rev1','rev2'])
        result=self.engine(e,w).run(INPUT)
        self.assertEqual((result['decision'],result['repairs']),('HUMAN REVIEW',2))
        second=next(r for r in result['history'][1]['rule_findings'] if r['rule_id']=='FR009')
        self.assertTrue(second['repeated_after_repair'])
        self.assertEqual(len(e.calls),3)
    def test_preservation_rule_needs_baseline(self):
        state,_=normalize(INPUT)
        self.assertNotIn('FR007',[r['rule_id'] for r in applicable(RULES,state)])
        state['previous_candidate']='previous correct text'
        self.assertIn('FR007',[r['rule_id'] for r in applicable(RULES,state)])
    def test_preservation_violation_on_recheck(self):
        e=RuleEvaluator([{'violations':['FR009']},{'violations':['FR007']},{}])
        w=Worker(['changed content','restored content'])
        result=self.engine(e,w).run(INPUT)
        self.assertEqual(result['decision'],'PASS')
        self.assertEqual(w.payloads[1]['failure_rules'][0]['rule_id'],'FR007')
        self.assertEqual(w.payloads[1]['required_correction']['preservation_reference'],INPUT['candidate_output'])
    def test_exact_required_json_keys_deterministic(self):
        data=copy.deepcopy(INPUT);data['candidate_output']='{"message":"Atlas"}'
        data['deterministic_checks']={'json_required_fields':['message','launch_date']}
        e=RuleEvaluator([{}]);w=Worker(['{"message":"Atlas","launch_date":"15 October 2026"}'])
        result=self.engine(e,w).run(data)
        self.assertEqual((result['decision'],len(e.calls)),('PASS',1))
        first=result['history'][0]
        self.assertIsNone(first['jev_results'])
        self.assertEqual(first['triggered_rule_ids'],['FR006'])
        self.assertEqual(first['rule_findings'][0]['method'],'deterministic')
        self.assertEqual(w.payloads[0]['failure_rules'][0]['rule_id'],'FR006')
    def test_future_pack_without_engine_change(self):
        custom=copy.deepcopy(RULES[4]);custom['rule_id']='CUSTOM001'
        custom['detector']={'kind':'deterministic','check_id':'required_substrings'}
        path=Path(self.tmp.name)/'pack.json'
        path.write_text(json.dumps({'schema_version':1,'pack_id':'extra','rules':[custom]}))
        loaded=load_packs([ROOT/'rules/universal.json',path],PROFILE)
        self.assertEqual(len(loaded),11)
        data=copy.deepcopy(INPUT);data['deterministic_checks']={'required_substrings':['Atlas']}
        result=self.engine(RuleEvaluator([{}]),rules=loaded).run(data)
        self.assertEqual(result['decision'],'PASS')
    def test_duplicate_rule_rejected(self):
        with self.assertRaises(EngineError):validate_rules(RULES+[RULES[0]],PROFILE)
    def test_malformed_severity_rejected(self):
        rules=copy.deepcopy(RULES);rules[0]['severity']='FATAL'
        with self.assertRaises(EngineError):validate_rules(rules,PROFILE)
        with self.assertRaises(EngineError):self.engine(RuleEvaluator([]),rules={})
    def test_reuse_semantics_cannot_silently_change(self):
        rules=copy.deepcopy(RULES);rules[0]['true_criteria']='different'
        with self.assertRaises(EngineError):validate_rules(rules,PROFILE)
    def test_failed_extra_response_review(self):
        result=self.engine(Evaluator([answer()])).run(INPUT)
        self.assertEqual(result['decision'],'HUMAN REVIEW')
    def test_uncertainty_original_policy_preserved(self):
        result=self.engine(RuleEvaluator([{'violations':['FR009'],'overrides':{'requirements_met':.5}}]),Worker([])).run(INPUT)
        self.assertEqual(result['decision'],'HUMAN REVIEW')
    def test_new_optional_baseline_normalizes(self):
        state,_=normalize(dict(INPUT,previous_candidate='before',allowed_changes=['Fix date']))
        self.assertEqual(state['allowed_changes'],['Fix date'])
    def test_no_rules_v1_questions_unchanged(self):
        e=RuleEvaluator([{}]);result=self.engine(e,rules=[]).run(INPUT)
        self.assertEqual(result['decision'],'PASS')
        self.assertEqual(e.calls[0]['questions'],PROFILE['questions'])
        self.assertEqual(e.calls[0]['state'],normalize(INPUT)[0])

if __name__=='__main__':unittest.main()
