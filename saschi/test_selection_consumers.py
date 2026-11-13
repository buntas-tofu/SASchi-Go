"""The separately marked finite selection consumer grammar and its refusals."""
from copy import deepcopy
import json,operator,unittest
from examples.verify_selection_consumers import GATE
from examples.wave_gate_common import assert_result
from .wave3_test_support import FamilyContract
from .test_do_counted import execute,job_with_inputs
from .plan import compile_plan
from .runtime import run_plan
from .job import build_job
from .emit_py import translate

PROFILE='function-consumers-v2'

class SelectionConsumerTests(unittest.TestCase):
    atomic_cli=FamilyContract.atomic_cli

    def test_complete_independent_original(self):
        GATE.qualify([]);inputs=json.loads(GATE.inputs.read_text())
        result,stdout=execute(GATE.source.read_text(),inputs)
        assert_result(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(s+'\n' for s in result['log']))
        self.assertEqual(list(result['datasets']['consumers']['schema'])[-6:],['status','chosen','identifier','cleaned','blanked','has_upper'])

    def test_all_five_qualified_shapes_select_the_new_marker(self):
        statements=["x=ifc(notalnum(code)=0,'OK','REVIEW')","x=ifc(notalnum(code) eq 0,'OK','REVIEW')",'x=ifn(flag,fallback,largest(k,a,b,c))',"x=cats(propcase(label,' -'),'-',dequote(code))","x=transtrn(label,'-',trimn(' '))",'if anyupper(code)>0 then x=1']
        for statement in statements:
            source='data d;length code $8;length label $12;code=\'ABcd1234\';label=\'A--b\';flag=1;fallback=7;k=1;a=3;b=1;c=2;'+statement+';run;'
            plan=compile_plan(source);self.assertFalse(plan.blocked,plan.tickets)
            self.assertEqual(plan.to_dict()['steps'][0]['operations'][0]['args'],{'profile':PROFILE})
            self.assertIn(('selection-consumers','DS-115',1),plan.matched)
            self.assertEqual(build_job(source).code,0)
            self.assertEqual(build_job(source,target='cpp').code,2)

    def test_zero_length_deletion_is_distinct_from_blank_replacement(self):
        source="data d;label='a-b';deleted=transtrn(label,'-',trimn(' '));blanked=transtrn(label,'-',' ');run;"
        result,_=execute(source);row=result['datasets']['d']['rows'][0]
        self.assertEqual(row['deleted'],'ab'.ljust(200));self.assertEqual(row['blanked'],'a b'.ljust(200))
        self.assertEqual(build_job("data d;x=transtrn('a-b','-','');run;").code,2)

    def test_ifn_evaluates_unselected_nested_rank(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[deepcopy(inputs['raw']['rows'][0])];inputs['raw']['rows'][0].update(flag=1,k=0)
        self.assertEqual(job_with_inputs(GATE.source.read_text(),inputs).code,1)
        source='data d;flag=1;fallback=9;x=ifn(flag,fallback,largest(0,1,2));run;'
        self.assertEqual(build_job(source).code,2)

    def test_late_unselected_rank_failure_is_atomic(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=inputs['raw']['rows'][:2];inputs['raw']['rows'][1].update(flag=1,k=0)
        self.atomic_cli(GATE.source.read_text(),inputs,'rank')

    def test_skipped_statement_does_not_evaluate_nested_rank(self):
        source='data d;set raw;if 0 then x=ifn(flag,fallback,largest(k,a,b,c));output;run;'
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=inputs['raw']['rows'][:1];inputs['raw']['rows'][0].update(k=0)
        result,_=execute(source,inputs)
        self.assertIsNone(result['datasets']['d']['rows'][0]['x'])

    def test_else_if_predicates_evaluate_only_when_reached(self):
        source='data d;set raw;if flag=1 then x=1;else if anypunct(code,start)>0 then x=2;else x=0;output;put x;run;'
        schema={'flag':'number','code':{'type':'character','length':8},'start':'number'}
        first={'flag':1,'code':'_','start':.5}
        result,_=execute(source,{'raw':{'schema':schema,'rows':[first]}})
        self.assertEqual(result['datasets']['d']['rows'][0]['x'],1.)
        self.atomic_cli(source,{'raw':{'schema':schema,'rows':[first,{**first,'flag':0}]}},'integral')
        self.assertEqual(build_job("data d;if 1 then x=1;else if anypunct('_',.5)>0 then x=2;run;").code,2)

    def test_empty_input_retains_all_inferred_descriptors(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['raw']['rows']=[]
        result,_=execute(GATE.source.read_text(),inputs)
        self.assertEqual(result['datasets']['consumers']['rows'],[])
        self.assertEqual(result['datasets']['consumers']['schema']['identifier'],{'type':'character','length':200})
        self.assertEqual(result['datasets']['consumers']['schema']['status'],{'type':'character','length':200})
        inputs['raw']['schema']['code']='number'
        self.assertEqual(job_with_inputs(GATE.source.read_text(),inputs).code,1)

    def test_exact_marker_is_required_and_not_user_data(self):
        original=compile_plan(GATE.source.read_text()).to_dict();inputs=json.loads(GATE.inputs.read_text())
        self.assertEqual(original['steps'][0]['operations'][0]['kind'],'function_profile')
        mutations=[]
        p=deepcopy(original);p['steps'][0]['operations'].pop(0);mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].append(p['steps'][0]['operations'].pop(0));mutations.append(p)
        p=deepcopy(original);p['steps'][0]['operations'].insert(1,deepcopy(p['steps'][0]['operations'][0]));mutations.append(p)
        for args in [{'profile':PROFILE,'extra':1},{'profile':'function-consumers-v1'},None,[],{'profile':['function-consumers-v2']}]:
            p=deepcopy(original);p['steps'][0]['operations'][0]['args']=args;mutations.append(p)
        p=deepcopy(original);p['version']=1;mutations.append(p)
        p=deepcopy(original);p['version']=True;mutations.append(p)
        for p in mutations:
            with self.assertRaises(ValueError):run_plan(p,inputs,allow_partial=True)

    def test_unnecessary_marker_and_mixed_profiles_refuse(self):
        p=compile_plan('data d;x=1;run;').to_dict();p['steps'][0]['operations'].insert(0,{'kind':'function_profile','line':1,'args':{'profile':PROFILE}})
        with self.assertRaises(ValueError):run_plan(p)
        original=compile_plan(GATE.source.read_text()).to_dict()
        old=compile_plan("data other;length a $4;a='a';x=upcase(strip(a));run;").to_dict()
        p=deepcopy(original);p['steps']+=old['steps']
        with self.assertRaises(ValueError):run_plan(p,json.loads(GATE.inputs.read_text()))

    def test_malformed_comparison_and_nested_calls_refuse_value_error(self):
        original=compile_plan(GATE.source.read_text()).to_dict();inputs=json.loads(GATE.inputs.read_text())
        assignment=next(i for i,op in enumerate(original['steps'][0]['operations']) if op['kind']=='assign' and op['args']['name']=='status')
        for change in ['kind','operator','right','left-name','left-args','extra']:
            p=deepcopy(original);expr=p['steps'][0]['operations'][assignment]['args']['value'];comparison=expr['args'][0]
            if change=='kind':comparison['kind']='arithmetic'
            elif change=='operator':comparison['op']='>'
            elif change=='right':comparison['right']={'kind':'number','value':1}
            elif change=='left-name':comparison['left']['name']=[]
            elif change=='left-args':comparison['left']['args']=None
            else:comparison['extra']=True
            with self.subTest(change=change),self.assertRaises(ValueError):run_plan(p,inputs)

    def test_marker_tree_cycles_depth_and_program_bounds(self):
        original=compile_plan(GATE.source.read_text()).to_dict();inputs=json.loads(GATE.inputs.read_text())
        p=deepcopy(original);p['steps'][0]['operations'][0]['args']['cycle']=p['steps'][0]
        with self.assertRaises(ValueError):run_plan(p,inputs)
        p=deepcopy(original);node={};p['steps'][0]['lengths']['deep']=node
        for _ in range(70):child={};node['x']=child;node=child
        with self.assertRaises(ValueError):run_plan(p,inputs)
        p=deepcopy(original);p['steps']=p['steps']*17
        with self.assertRaises(ValueError):run_plan(p,inputs)
        p=deepcopy(original);extra=deepcopy(next(op for op in p['steps'][0]['operations'] if op['kind']=='assign'));p['steps'][0]['operations']+= [deepcopy(extra) for _ in range(257)]
        with self.assertRaises(ValueError):run_plan(p,inputs)

    def test_selected_IF_operators_match_independent_position_oracle(self):
        names=['anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace']
        operators={'=':operator.eq,'eq':operator.eq,'^=':operator.ne,'~=':operator.ne,'<>':operator.ne,'ne':operator.ne,'<':operator.lt,'lt':operator.lt,'>':operator.gt,'gt':operator.gt,'<=':operator.le,'le':operator.le,'>=':operator.ge,'ge':operator.ge}
        positions=GATE.r_cases([('pos:'+name,['aZ9_ f  ']) for name in names])
        for name,position in zip(names,positions):
            for spelling,compare in operators.items():
                for rhs in [0,1,8]:
                    source="data d;length code $8;code='aZ9_ f';if "+name+'(code) '+spelling+' '+str(rhs)+' then x=1;else x=0;run;'
                    result,_=execute(source);self.assertEqual(result['datasets']['d']['rows'][0]['x'],float(compare(position,rhs)))

    def test_late_CATS_buffer_failure_is_atomic(self):
        schema={'label':{'type':'character','length':120},'code':{'type':'character','length':100}}
        inputs={'raw':{'schema':schema,'rows':[{'label':'A','code':'B'},{'label':'X'*120,'code':'Y'*100}]}}
        source="data d;set raw;key=cats(propcase(label,' -'),'-',dequote(code));output;put key;run;"
        self.atomic_cli(source,inputs,'CAT')
        short="data d;length x $1;set raw;if 0 then x=cats(propcase('a b',' '));run;"
        self.assertIn(job_with_inputs(short,{'raw':{'schema':{'n':'number'},'rows':[]}}).code,(1,2))

    def test_held_shapes_and_profile_joins_remain_refused(self):
        roots=["ifc(anyupper(code)>0,'Y','N')",'ifn(flag,largest(k,a,b,c),fallback)',"cats(quote(code))","cats(propcase(dequote(code),' '))","transtrn(label,'-',trimn('  '))"]
        setup="data d;length code $8;length label $12;code='A';label='A';flag=1;fallback=9;k=1;a=1;b=2;c=3;"
        self.assertEqual(build_job(setup+'run;').code,0)
        for root in roots:self.assertIn(build_job(setup+'x='+root+';run;').code,(1,2))
        for prefix in ['retain z 0;','array z a b;','do i=1 to 1;']:
            source=setup+prefix+"x=transtrn(label,'-',trimn(' '));"+('end;' if prefix.startswith('do ') else '')+'run;'
            self.assertIn(build_job(source).code,(1,2))
        for statement in ['if anyupper(code) then x=1;','if anyupper(code)>0 and flag=1 then x=1;','if 0<anyupper(code) then x=1;']:
            self.assertIn(build_job(setup+statement+'run;').code,(1,2))

    def test_v1_standalone_profile_and_emission_remain_deterministic(self):
        source="data d;length a $4;a=' a ';x=upcase(strip(a));run;";plan=compile_plan(source)
        self.assertFalse(plan.blocked,plan.tickets)
        self.assertEqual(plan.to_dict()['steps'][0]['operations'][0]['args'],{'profile':'function-consumers-v1'})
        from examples.verify_missing_summaries import GATE as missing_gate
        targets=missing_gate.r_cases([('missing',[value]) for value in ['    ','A   ']])
        for literal,wanted in zip([' ','A'],targets):
            shared=compile_plan("data d;length a $4;a='"+literal+"';if missing(a)=1 then x=1;else x=0;run;").to_dict()
            self.assertEqual(shared['steps'][0]['operations'][0]['args'],{'profile':'function-consumers-v1'})
            shared['steps'][0]['operations'][0]['args']={'profile':PROFILE}
            shared['matched'].append(('selection-consumers','DS-115',1))
            self.assertEqual(run_plan(shared)['datasets']['d']['rows'][0]['x'],wanted)
        self.assertEqual(translate(GATE.source.read_text()).code,translate(GATE.source.read_text()).code)
        p=compile_plan(GATE.source.read_text()).to_dict();saved=deepcopy(p);inputs=json.loads(GATE.inputs.read_text());before=deepcopy(inputs)
        run_plan(p,inputs);self.assertEqual((p,inputs),(saved,before))

if __name__=='__main__':unittest.main()
