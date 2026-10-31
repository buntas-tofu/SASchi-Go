"""Independent DS-060/061 source, portable, state and resource boundaries."""
from copy import deepcopy
import contextlib
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_grouped_control import (ORIGINAL,PROFILE,original_expected,
    original_trace,hand_cases,refusal_cases,promotion_cases,batch_witness,execute,
    cli_check,wrong_comparators,case)
from saschi.compare import equal
from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.grouped_control import validate_step
from saschi.emit_py import translate
from saschi.emit_cpp import translate as cpp_translate
from saschi.job import build_job

ROOT=Path(__file__).resolve().parents[1]
EXACT_PROMOTED=(
 'data d; x=1; if 0 then do; x=2; end; put x=; run;',
 'data _null_; x=1; if 0 then do; x=2; end; put x=; run;',
 'data d; if 1 then do; x=2; end; run;',
 'data d; do i=1 to 2; if 1 then do; x=7; end; end; run;',
 'data d; do i=1 to 2; if 1 then leave; end; run;',
 'data d; do i=1 to 2; if 1 then continue; end; run;',
 'data d; if 1 then x=7; else do; x=9; end; run;',
 'data d; do i=1 to 2; leave; end; run;',
 'data d; n=2; do i=1 to n; leave; end; run;',
 'data d; do i=1 to 2; continue; end; run;',
 'data d; n=2; do i=1 to n; continue; end; run;')
ZERO_VARIABLE_REFUSALS=(
 'data d; do until(1); leave; end; run;',
 'data d; do while(0); leave; end; run;',
 'data d; do until(1); continue; end; run;',
 'data d; do while(0); continue; end; run;')


def hand_result(names,values,log=(),destination='d'):
    return {'datasets':{} if destination=='_null_' else {destination:{'schema':dict.fromkeys(names.split(),'number'),
            'rows':[dict(zip(names.split(),values))]}},'log':list(log)}


PROMOTION_EXPECTED=(hand_result('x',[1.],['x=1']),hand_result('',[],['x=1'],'_null_'),
    hand_result('x',[2.]),hand_result('i x',[3.,7.]),hand_result('i',[1.]),hand_result('i',[3.]),
    hand_result('x',[7.]),hand_result('i',[1.]),hand_result('n i',[2.,1.]),
    hand_result('i',[3.]),hand_result('n i',[2.,3.]))


def compiled(source):
    plan=compile_plan(source)
    if plan.blocked:raise AssertionError(plan.tickets)
    return plan.to_dict()


def run(source,catalog=None):return run_plan(compiled(source),catalog)


def assert_cli_result(test,source,expected,catalog=None):
    if expected['datasets']:
        return cli_check(source,catalog,expected)
    # --expect requires at least one dataset. DATA _NULL_ keeps its existing
    # actual job/result/log comparison without changing that CLI contract.
    with tempfile.TemporaryDirectory() as directory:
        folder=Path(directory);path=folder/'program.sas';path.write_text(source)
        inputs=folder/'inputs.json';inputs.write_text(json.dumps({} if catalog is None else catalog));out=folder/'job'
        process=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--inputs',str(inputs),'--output',str(out)],cwd=ROOT,capture_output=True,text=True,timeout=45)
        receipt=json.loads((out/'receipt.json').read_text())
        test.assertEqual(process.returncode,0,process.stdout+process.stderr);test.assertTrue(receipt['accepted'])
        test.assertTrue(equal(json.loads((out/'result.json').read_text()),expected,ordered_maps=True))
        test.assertEqual(receipt['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        return receipt


@lru_cache(maxsize=11)
def promotion_witness(source):return batch_witness([case('exact_promotion',source)])[0]


def assert_promoted_source(test,source):
    """Keep each exact historical source and prove both sides of its boundary."""
    test.assertIn(source,EXACT_PROMOTED)
    expected=PROMOTION_EXPECTED[EXACT_PROMOTED.index(source)]
    plan=compiled(source);test.assertEqual(plan['steps'][0]['kind'],'control_data')
    test.assertEqual(plan['steps'][0]['operations'][0]['args'],{'name':PROFILE})
    observed=execute(source,emitted=True);test.assertTrue(equal(observed['result'],expected,ordered_maps=True))
    independent=promotion_witness(source);test.assertIsNotNone(independent)
    test.assertTrue(equal(independent['result'],expected,ordered_maps=True))
    test.assertEqual(observed['trace'],independent['trace'])
    for remove in (False,True):
        older=deepcopy(plan);older['steps'][0]['kind']='data'
        if remove:older['steps'][0]['operations'].pop(0)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),test.assertRaises(ValueError):run_plan(older)
        test.assertEqual(stream.getvalue(),'')
    for marker in ('binary64-v1','binary64-rows-v1','binary64-pipeline-v1'):
        older=deepcopy(plan);older['steps'][0]['kind']='data'
        older['steps'][0]['operations'][0]={'kind':'numeric_profile','line':older['steps'][0]['line'],'args':{'name':marker}}
        with test.assertRaises(ValueError):run_plan(older)
    return observed


class GroupedControlTests(unittest.TestCase):
    def assert_result(self,source,expected,catalog=None,independent=True):
        observed=execute(source,catalog,emitted=True)
        self.assertTrue(equal(observed['result'],expected,ordered_maps=True),(observed['result'],expected))
        if independent:
            r=batch_witness([case('test',source,catalog=catalog)])[0];self.assertIsNotNone(r)
            self.assertTrue(equal(r['result'],expected,ordered_maps=True));self.assertEqual(r['trace'],observed['trace'])
        return observed

    def assert_refused(self,source,catalog=None):
        parsed=compile_plan(source)
        if not parsed.blocked:
            with self.assertRaises(ValueError):run_plan(parsed.to_dict(),catalog)

    def test_group_hand_pins_and_events(self):
        cases=hand_cases('group');seen=batch_witness(cases)
        for c,r in zip(cases,seen):
            with self.subTest(name=c['name']):
                self.assertIsNotNone(r);o=execute(c['source'],c['catalog'],emitted=True)
                self.assertTrue(equal(o['result'],c['expected'],ordered_maps=True))
                self.assertTrue(equal(r['result'],c['expected'],ordered_maps=True));self.assertEqual(o['trace'],r['trace'])

    def test_transfer_hand_pins_and_events(self):
        cases=hand_cases('transfer');seen=batch_witness(cases)
        for c,r in zip(cases,seen):
            with self.subTest(name=c['name']):
                self.assertIsNotNone(r);o=execute(c['source'],c['catalog'],emitted=True)
                self.assertTrue(equal(o['result'],c['expected'],ordered_maps=True));self.assertEqual(o['trace'],r['trace'])
                if c['trace'] is not None:self.assertEqual(o['trace'],c['trace'])

    def test_exact_eleven_source_promotions_and_actual_cli(self):
        cases=promotion_cases();self.assertEqual(tuple(c['source'] for c in cases),EXACT_PROMOTED)
        for c,expected in zip(cases,PROMOTION_EXPECTED):
            self.assertTrue(equal(c['expected'],expected,ordered_maps=True))
            assert_promoted_source(self,c['source']);assert_cli_result(self,c['source'],expected)

    def test_four_exact_zero_variable_sources_remain_refused(self):
        for source in ZERO_VARIABLE_REFUSALS:
            self.assertTrue(compile_plan(source).blocked,source)
        self.assertEqual(batch_witness([case('zero_variable',s) for s in ZERO_VARIABLE_REFUSALS]),[None]*4)

    def test_original_whole_source_result_trace_stdout_and_cli(self):
        source=ORIGINAL.read_text();expected=original_expected();observed=execute(source,emitted=True)
        self.assertTrue(equal(observed['result'],expected,ordered_maps=True));self.assertEqual(observed['trace'],original_trace())
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'a4355e2c445c3626d1b4c00dae698bfe6c896f54ccd47cc70aea58c48c2b08eb')
        self.assertEqual(hashlib.sha256(json.dumps(expected,separators=(',',':')).encode()).hexdigest(),'7f456b0d33b1a0866fb112b1e5c13a5b6b923fd8c2a66817465f4f4c1a3745ba')
        self.assertEqual(hashlib.sha256(json.dumps(original_trace(),separators=(',',':')).encode()).hexdigest(),'5a7240539b5a57cbb3ca3615b94b9d378d17accf8069c6df24ac99db9a5da971')
        self.assertEqual(hashlib.sha256(''.join(line+'\n' for line in expected['log']).encode()).hexdigest(),'3ff580a2f4bc01b60f96a822e39b8c0a4095d11c64d9a699411988da119e28e4')
        self.assertEqual(len(observed['trace']),172)
        self.assertEqual(sum(len(t['rows']) for t in expected['datasets'].values()),9)
        r=batch_witness([case('original',source)])[0];self.assertIsNotNone(r)
        self.assertTrue(equal(r['result'],expected,ordered_maps=True));self.assertEqual(r['trace'],original_trace())
        self.assertEqual(r['accounting'],{'statements':57,'steps':[{'name':'seed','iterations':1,'trips':0},{'name':'measured','iterations':3,'trips':13},{'name':'fresh','iterations':1,'trips':3}]})
        cli_check(source,expected=expected)

    def test_groups_are_transparent_to_nearest_iterative_owner(self):
        source='data d;x=0;do i=1 to 2;do j=3 to 1 by -1;do;if j=2 then do;leave;end;x=x+1;end;end;x=x+10;end;run;'
        self.assert_result(source,hand_result('x i j',[22.,3.,2.]))
        source='data d;x=0;do i=1 to 2;do j=3 to 1 by -1;do;if j=2 then do;continue;end;x=x+1;end;end;x=x+10;end;run;'
        self.assert_result(source,hand_result('x i j',[24.,3.,0.]))

    def test_until_continue_tests_bottom_and_leave_bypasses_it(self):
        self.assert_result('data d;n=0;do until(n>=1);do;n=n+1;continue;n=99;end;end;run;',hand_result('n',[1.]))
        self.assert_result('data d;n=2147483647;do until(n+1>0);do;leave;end;end;run;',hand_result('n',[2147483647.]))
        source='data d;n=2147483647;do until(n+1>0);do;continue;end;end;run;'
        self.assertFalse(compile_plan(source).blocked)
        with self.assertRaises(ValueError):run(source)
        self.assertEqual(batch_witness([case('reached_bottom_overflow',source)]),[None])

    def test_counted_controls_capture_once_and_leave_keeps_current_index(self):
        source='data d;stop=3;delta=1;x=0;do i=1 to stop by delta;do;stop=1;delta=2;x=x+i;end;end;run;'
        self.assert_result(source,hand_result('stop delta x i',[1.,2.,6.,4.]))
        source='data d;do i=2147483647 to 2147483647 by 2147483647;leave;end;run;'
        self.assert_result(source,hand_result('i',[2147483647.]))
        bad=source.replace('leave;','continue;');self.assertFalse(compile_plan(bad).blocked)
        with self.assertRaises(ValueError):run(bad)

    def test_own_index_and_active_indices_guard_every_descendant(self):
        for key,header in [('start','i=i to 3'),('stop','i=1 to i'),('by','i=1 to 3 by i')]:
            for branch in ('do;','if 0 then do;'):
                text='data d;i=1;'+branch+'do '+header+';x=i;end;end;run;'
                self.assertTrue(compile_plan(text).blocked,(key,text))
        for action in ('i=3;','i+1;','if 0 then i=3;','if 1 then x=7;else i=3;',
                       'do j=1 to 2;do;if 0 then i=3;end;end;'):
            text='data d;x=0;do i=1 to 2;do;'+action+'end;end;run;'
            self.assertTrue(compile_plan(text).blocked,action)
        plan=compiled('data d;x=1;do i=1 to 2;do;x=x+1;end;end;run;')
        loop=plan['steps'][0]['operations'][2];loop['args']['stop']={'kind':'variable','value':'i'}
        with self.assertRaises(ValueError):run_plan(plan)

    def test_zero_and_ten_thousand_trip_schedules(self):
        self.assert_result('data d;x=7;do i=3 to 1;continue;end;run;',hand_result('x i',[7.,3.]))
        source='data d;x=7;do i=1 to 10000;leave;end;run;'
        self.assertEqual(run(source)['datasets']['d']['rows'],[{'x':7.,'i':1.}])
        self.assertTrue(compile_plan(source.replace('10000','10001')).blocked)
        boundaries=[]
        for kind,test in [('while','n<10000'),('until','n>=10000')]:
            text=f'data d;n=0;do {kind}({test});n=n+1;continue;end;run;'
            self.assertEqual(run(text)['datasets']['d']['rows'],[{'n':10000.}])
            boundaries.append(case(kind,text))
            self.assertFalse(compile_plan(text.replace('10000','10001')).blocked)
            with self.assertRaises(ValueError):run(text.replace('10000','10001'))
        for c,r in zip(boundaries,batch_witness(boundaries)):
            self.assertIsNotNone(r);self.assertEqual(r['result']['datasets']['d']['rows'],[{'n':10000.}])
            self.assertEqual(sum(event.startswith('iteration|'+c['name']+'|') for event in r['trace']),10000)

    def test_shared_planned_trip_reservation_and_per_observation_reset(self):
        text='data d;x=0;do i=1 to 2;do j=1 to 4999;leave;end;x=x+1;end;run;'
        self.assert_result(text,hand_result('x i j',[2.,3.,1.]))
        bad=text.replace('4999','5000');self.assertFalse(compile_plan(bad).blocked)
        with self.assertRaises(ValueError):run(bad)
        catalog={'raw':{'schema':{'id':'number'},'rows':[{'id':1.},{'id':2.}]}}
        source=text.replace('data d;','data d;set raw;')
        result=run(source,catalog);self.assertEqual([r['x'] for r in result['datasets']['d']['rows']],[2.,2.])

    def test_eight_counted_loop_levels_and_ninth_refusal(self):
        def source(n):return 'data d;x=1;' + ''.join(f'do i{k}=1 to 1;' for k in range(n))+'do;x=x+1;end;'+'end;'*n+'run;'
        self.assertEqual(run(source(8))['datasets']['d']['rows'][0]['x'],2.)
        self.assertIsNotNone(batch_witness([case('eight_nested',source(8))])[0])
        self.assertTrue(compile_plan(source(9)).blocked)
        self.assertTrue(compile_plan('data d;x=1;do i=1 to 1;do while(0);leave;end;end;run;').blocked)

    def test_mixed_depth_and_expression_depth_are_separate_bounded_axes(self):
        leaf='x='+'1'+'+0'*31+';';text='data d;'+'if 1 then do;'*16+leaf+'end;'*16+'run;'
        self.assertEqual(run(text)['datasets']['d']['rows'],[{'x':1.}])
        self.assertIsNotNone(batch_witness([case('32mixed_32expression',text)])[0])
        self.assertTrue(compile_plan('data d;'+'if 1 then do;'*17+'x=1;'+'end;'*17+'run;').blocked)
        self.assertTrue(compile_plan(text.replace('+0;','+0+0;',1)).blocked)

    def test_exact_expanded_operation_and_arithmetic_node_bounds(self):
        good='data d;do;'+'x=1;'*1023+'end;run;';self.assertEqual(run(good)['datasets']['d']['rows'],[{'x':1.}])
        self.assertTrue(compile_plan(good.replace('end;run;','x=1;end;run;')).blocked)
        plan=compiled(good);group=plan['steps'][0]['operations'][1];group['args']['body'].append(deepcopy(group['args']['body'][0]))
        with self.assertRaises(ValueError):run_plan(plan)
        text='data d;do;'+'x=1+0;'*128+'end;run;';self.assertEqual(run(text)['datasets']['d']['rows'],[{'x':1.}])
        self.assertTrue(compile_plan(text.replace('end;run;','x=1+0;end;run;')).blocked)

    def test_full_pdv_width_before_output_selection(self):
        good='data d(keep=x1);do;'+''.join(f'x{i}=1;' for i in range(1,65))+'end;run;'
        self.assertEqual(run(good)['datasets']['d'],{'schema':{'x1':'number'},'rows':[{'x1':1.}]})
        self.assertTrue(compile_plan(good.replace('end;run;','x65=1;end;run;')).blocked)
        for text in ('data d;do;end;run;','data _null_;do;put "A";end;run;'):
            self.assertTrue(compile_plan(text).blocked)

    def test_selected_eager_integer_domain_and_empty_descriptor_validation(self):
        text='data d;set raw;do;x=0;if 0 then output;end;run;'
        for value in (.5,True,{'missing':'A'},2147483648.):
            raw={'raw':{'schema':{'x':'number','unused':'number'},'rows':[{'x':1.,'unused':value}]}}
            with self.assertRaises(ValueError):run(text,raw)
        for spec in ({'type':'character','length':4},{'type':'number','length':4}):
            with self.assertRaises(ValueError):run(text,{'raw':{'schema':{'x':spec},'rows':[]}})

    def test_excluded_values_and_metadata_transport_exactly_without_mutation(self):
        text='data d;set raw(keep=x);do;y=x;end;run;'
        for value in (.5,.1,2147483647.5,{'missing':'A'}):
            catalog={'raw':{'encoding':'latin-1','label':'caf\u00e9','schema':{'x':{'type':'number','length':8,'label':'X','format':''},'other':'number'},'rows':[{'x':1.,'other':value}]}}
            before=deepcopy(catalog);observed=execute(text,catalog,emitted=True);self.assertEqual(catalog,before)
            self.assertTrue(equal(observed['result']['datasets']['raw'],catalog['raw'],ordered_maps=True))
            r=batch_witness([case('excluded_metadata',text,catalog=catalog)])[0];self.assertIsNotNone(r)
            self.assertTrue(equal(r['result'],observed['result'],ordered_maps=True),(value,r,observed))

    def test_excluded_character_is_preserved_but_selected_character_refuses(self):
        catalog={'raw':{'encoding':'latin-1','label':'caf\u00e9','schema':{'x':'number','text':{'type':'character','length':4,'label':'r\u00e9f','format':''}},'rows':[{'x':1.,'text':'\u00e9   '}]}}
        text='data d;set raw(keep=x);do;y=x;end;run;';observed=execute(text,catalog,emitted=True)
        r=batch_witness([case('excluded_character',text,catalog=catalog)])[0];self.assertIsNotNone(r)
        self.assertTrue(equal(r['result'],observed['result'],ordered_maps=True))
        with self.assertRaises(ValueError):run(text.replace('(keep=x)',''),catalog)

    def test_selected_unprinted_format_survives_but_printing_it_refuses_empty(self):
        for rows in ([],[{'x':1.}]):
            raw={'raw':{'schema':{'x':{'type':'number','label':'','format':'8.'}},'rows':rows}}
            source='data d;set raw;do;y=x;end;run;';result=run(source,raw)
            self.assertEqual(result['datasets']['d']['schema']['x'],raw['raw']['schema']['x'])
            bad=source.replace('y=x;','y=x;put x;')
            with self.assertRaises(ValueError):run(bad,raw)

    def test_static_dead_and_empty_paths_validate_but_dynamic_skips_are_lazy(self):
        raw={'raw':{'schema':{'x':'number'},'rows':[]}}
        for body in ('if 0 then bad=.5;','do while(0);bad=2147483647+1;end;',
                     'do i=1 to 1;leave;bad=.5;end;','if 0 then bad=sin(0);'):
            self.assertTrue(compile_plan('data d;set raw;do;'+body+'end;run;').blocked)
        text='data d;set raw;do;if 0 then x=x+1;future=7;end;run;'
        self.assertEqual(run(text,raw)['datasets']['d']['rows'],[])
        raw['raw']['rows']=[{'x':2147483647.}];self.assertEqual(run(text,raw)['datasets']['d']['rows'],[{'x':2147483647.,'future':7.}])

    def test_pdv_reset_imported_sum_overwrite_and_early_snapshots(self):
        source='data d;retain saved 0;set raw;do;before=scratch;scratch=x;total+x;output;saved+total;output;end;run;'
        raw={'raw':{'schema':{'x':'number','total':'number'},'rows':[{'x':2.,'total':10.},{'x':None,'total':None}]}}
        rows=run(source,raw)['datasets']['d']['rows'];self.assertEqual([r['total'] for r in rows],[12.,12.,0.,0.])
        self.assertEqual([r['saved'] for r in rows],[0.,12.,12.,12.]);self.assertTrue(all(r['before'] is None for r in rows))
        self.assertEqual([r['scratch'] for r in rows],[2.,2.,None,None])

    def test_explicit_output_discovery_after_skipped_and_unconditional_transfer(self):
        for text in ('data d;x=1;if 0 then do;future=2;output;end;run;',
                     'data d;x=1;do i=1 to 1;leave;output;end;run;'):
            self.assertEqual(run(text)['datasets']['d']['rows'],[])
        text='data d;x=1;do;output;x=2;output;end;run;'
        self.assertEqual(run(text)['datasets']['d']['rows'],[{'x':1.},{'x':2.}])

    def test_step_plan_catalog_and_projection_are_private(self):
        text='data d(keep=x);set raw(drop=other);do;before=x;x=99;output;end;run;'
        raw={'raw':{'schema':{'x':'number','other':{'type':'character','length':2}},'rows':[{'x':1.,'other':'AB'}]}}
        plan=compiled(text);p=deepcopy(plan);c=deepcopy(raw);result=run_plan(plan,raw)
        self.assertEqual(plan,p);self.assertEqual(raw,c)
        self.assertEqual(result['datasets']['d'],{'schema':{'x':'number'},'rows':[{'x':99.}]})

    def test_forged_step_marker_and_operation_fields_refuse_even_empty(self):
        original=compiled('data d;set raw;do;x=1;end;run;');empty={'raw':{'schema':{'x':'number'},'rows':[]}}
        for field,value in [('extra','ignored'),('retained',{'ghost':{'kind':'number','value':0}}),('kind','data'),('nodupkey',0),('lengths',{'x':3}),('display_names',{'x':'x'}),('where',{}),('line',True)]:
            p=deepcopy(original);p['steps'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):run_plan(p,empty)
        for version in (2.0,True,'2',None):
            p=deepcopy(original);p['version']=version
            with self.assertRaises(ValueError):run_plan(p,empty)
        for marker in ('other','binary64-v1','binary64-rows-v1','binary64-pipeline-v1'):
            p=deepcopy(original);p['steps'][0]['operations'][0]['args']['name']=marker
            with self.assertRaises(ValueError):run_plan(p,empty)
        for change in ('missing','nested','duplicate','extra','stale'):
            p=deepcopy(original);roots=p['steps'][0]['operations'];marker=deepcopy(roots[0])
            if change=='missing':roots.pop(0)
            elif change=='nested':roots[-1]['args']['body'].append(marker)
            elif change=='duplicate':roots.append(marker)
            elif change=='stale':roots[-1]=deepcopy(roots[-1]['args']['body'][0])
            else:roots[-1]['args']['body'][0]['args']['unknown']=True
            with self.subTest(change=change),self.assertRaises(ValueError):run_plan(p,empty)
        for value in ({'kind':'number','value':True},{'kind':'number','value':.5},{'kind':'number','value':float('inf')},
                      {'kind':'number','value':None},{'kind':'missing','value':1},{'kind':'variable','value':'_error_'},
                      {'kind':'automatic','value':'first.x'},{'kind':'tagged_missing','value':{'missing':'A'}}):
            p=deepcopy(original);p['steps'][0]['operations'][-1]['args']['body'][0]['args']['value']=value
            with self.subTest(value=value),self.assertRaises(ValueError):run_plan(p,empty)

    def test_forged_transfer_ownership_and_legacy_profile_refusals(self):
        original=compiled('data d;x=1;do i=1 to 1;do;leave;end;end;run;')
        for kind in ('leave','continue'):
            p=deepcopy(original);p['steps'][0]['operations']=[p['steps'][0]['operations'][0],{'kind':'assign','line':1,'args':{'name':'x','value':{'kind':'number','value':1}}},{'kind':kind,'line':1,'args':{}}]
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['kind']='data';p['steps'][0]['operations'].pop(0)
        with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['operations'][-1]['args']['body'][0]['args']['body'][0]['args']={'target':'outside'}
        with self.assertRaises(ValueError):run_plan(p)

        legacy=compiled('data d;x=1;run;')
        leaf=legacy['steps'][0]['operations'][0]
        legacy['steps'][0]['operations']=[deepcopy(leaf) for _ in range(20001)]
        before=json.dumps(legacy,separators=(',',':'))
        self.assertEqual(run_plan(legacy),hand_result('x',[1.]))
        self.assertEqual(json.dumps(legacy,separators=(',',':')),before)
        hidden={'kind':'if','line':1,'args':{'condition':{'op':'truth','left':{'kind':'number','value':0}},
                'operation':{'kind':'do_group','line':1,'args':{'body':[]}}}}
        for position in (0,len(legacy['steps'][0]['operations'])):
            forged=deepcopy(legacy);forged['steps'][0]['operations'].insert(position,deepcopy(hidden))
            with self.subTest(hidden_position=position),self.assertRaises(ValueError):run_plan(forged)

    def test_cycles_and_non_json_structures_refuse(self):
        p=compiled('data d;x=1;do;x=2;end;run;');group=p['steps'][0]['operations'][-1];group['args']['body'].append(group)
        with self.assertRaises(ValueError):run_plan(p)
        p=compiled('data d;x=1;do;x=2;end;run;');p['steps'][0]['operations'][-1]['args']['body']=()
        with self.assertRaises(ValueError):run_plan(p)

    def test_output_log_and_input_observation_limits_reset_by_step(self):
        text='data d;x=0;do i=1 to 10000;output;continue;end;run;'
        self.assertEqual(len(run(text)['datasets']['d']['rows']),10000)
        with self.assertRaises(ValueError):run(text.replace('end;run;','end;output;run;'))
        text='data _null_;x=1;do i=1 to 10000;put x;continue;end;run;'
        self.assertEqual(len(run(text)['log']),10000)
        with self.assertRaises(ValueError):run(text.replace('end;run;','end;put x;run;'))
        step='data _null_;x=1;do i=1 to 5001;do;put x;end;end;run;'
        result=execute(step+step,emitted=True);self.assertEqual(len(result['result']['log']),10002)
        r=batch_witness([case('per_step_records',step+step)])[0];self.assertIsNotNone(r)
        self.assertTrue(equal(r['result'],result['result'],ordered_maps=True))
        source='data d;set raw;do;x=0;end;run;'
        raw={'raw':{'schema':{'x':'number'},'rows':[{'x':1.}]*10000}}
        self.assertEqual(len(run(source,raw)['datasets']['d']['rows']),10000)
        raw['raw']['rows'].append({'x':1.})
        with self.assertRaises(ValueError):run(source,raw)

    def test_exact_million_event_limit_without_materializing_trace(self):
        prefix='data d;n=0;x=0;do while(n<9999);do;n=n+1;'+'x=1;'*95+'end;end;'
        accepted=prefix+'x=1;'*94+'run;'
        self.assertEqual(run(accepted)['datasets']['d']['rows'],[{'n':9999.,'x':1.}])
        with self.assertRaises(ValueError):run(prefix+'x=1;'*95+'run;')

    def test_actual_wrong_dataset_log_and_trace_controls(self):
        self.assertEqual(wrong_comparators('group'),8)
        self.assertEqual(wrong_comparators('transfer'),8)

    def test_late_failure_keeps_result_and_stdout_atomic(self):
        source='data early;x=1;do;put x;output;end;run;data late;x=2147483647;do;x=x+1;end;run;'
        parsed=compile_plan(source);self.assertFalse(parsed.blocked)
        job=build_job(source);self.assertNotEqual(job.code,0);self.assertIsNone(job.result)
        stream=io.StringIO();namespace={}
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,namespace)
        self.assertEqual(stream.getvalue(),'');self.assertNotIn('result',namespace)
        cli_check(source)

    def test_no_extra_numerical_input_array_control_or_cpp_scope(self):
        for old_source in ('data _null_;put \"do; leave; continue;\";run;',
                           'data d;leave=1;continue=2;do=3;run;',
                           'data d;input x;datalines;\n1 continue\n;\nrun;'):
            old_plan=compiled(old_source);self.assertTrue(all(step['kind']=='data' for step in old_plan['steps']))
            run_plan(old_plan)
        for text in ('data d;x=1;do;x=sin(0);end;run;','data d;array a{1}x;do;x=1;end;run;',
                     'data d;input x;do;x=1;end;datalines;\n1\n;\nrun;',
                     'data d;x=1;do;goto label;end;run;', 'data d;x=1;do;stop;end;run;'):
            self.assertTrue(compile_plan(text).blocked,text)
        source='data _null_;x=1;do;put x;end;run;';self.assertFalse(compile_plan(source).blocked)
        self.assertTrue(cpp_translate(source).blocked)


if __name__=='__main__':unittest.main()
