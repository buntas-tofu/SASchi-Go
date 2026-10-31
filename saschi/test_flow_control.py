"""Bounded local control source, state, portable and publication contracts."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from saschi.plan import compile_plan
from saschi.runtime import run_plan
from saschi.emit_py import translate
from saschi.emit_cpp import translate as cpp_translate
from saschi.compare import equal

ROOT=Path(__file__).resolve().parents[1]


def compiled(source):
    plan=compile_plan(source)
    if plan.blocked:raise AssertionError(plan.tickets)
    return plan.to_dict()


def execute(source):return run_plan(compiled(source))


class FlowControlTests(unittest.TestCase):
    def test_stage1_triangular_first_step_is_only_partial_external_evidence(self):
        import os
        corpus=Path(os.environ.get('SASCHI_ROKU_CORPUS',ROOT.parent/'saschi-roku/corpus'))
        source=(corpus/'flow_control_structures.sas').read_text().split('/* LINK:')[0]
        expected={'datasets':{},'log':[f'{n} {p} ' for p in range(1,11) for n in range(1,p+1)]}
        self.assertTrue(equal(execute(source),expected,ordered_maps=True))
        stream=io.StringIO();ns={}
        with contextlib.redirect_stdout(stream):exec(translate(source).code,ns)
        self.assertTrue(equal(ns['result'],expected,ordered_maps=True))
        self.assertEqual(stream.getvalue(),''.join(x+'\n' for x in expected['log']))

    def test_goto_labels_do_not_create_PDV_columns_or_merge_namespaces(self):
        source='data d;gcd=7;x=1;goto gcd;x=99;gcd:put gcd x;run;'
        result=execute(source)
        self.assertEqual(list(result['datasets']['d']['schema']),['gcd','x'])
        self.assertEqual(result['datasets']['d']['rows'],[{'gcd':7.,'x':1.}])
        self.assertEqual(result['log'],['7 1 '])

    def test_stop_preserves_explicit_snapshots_and_continues_later_steps(self):
        result=execute('data d;x=1;output;x=2;stop;x=99;run;data next;y=3;run;')
        self.assertEqual(result['datasets']['d']['rows'],[{'x':1.}])
        self.assertEqual(result['datasets']['next']['rows'],[{'y':3.}])
        self.assertEqual(execute('data d;x=1;stop;run;')['datasets']['d']['rows'],[])

    def test_stop_propagates_without_counted_increment_or_conditional_test(self):
        self.assertEqual(execute('data d;do i=2147483647 to 2147483647 by 2147483647;output;stop;end;run;')['datasets']['d']['rows'],[{'i':2147483647.}])
        self.assertEqual(execute('data d;x=2147483647;do until(x+1);do;output;stop;end;end;run;')['datasets']['d']['rows'],[{'x':2147483647.}])

    def test_static_labels_and_dead_branches_are_validated(self):
        for source in ('data d;x=1;if 0 then goto absent;run;',
                       'data d;x=1;a:x=2;A:stop;run;',
                       'data d;x=1;do;a:x=2;end;goto a;run;',
                       'data d;x=1;a:x=2;do;goto a;end;run;',
                       'data d;x=1;if 0 then do;goto a;end;a:stop;run;',
                       'data d;x=1;goto next;next:x=sin(0);run;'):
            self.assertTrue(compile_plan(source).blocked,source)

    def test_forged_old_profiles_and_malformed_new_marker_refuse(self):
        good=compiled('data d;x=1;done:stop;run;')
        for kind in ('data','control_data'):
            old=deepcopy(good);old['steps'][0]['kind']=kind
            with self.assertRaises(ValueError):run_plan(old)
            old['steps'][0]['operations'].pop(0)
            with self.assertRaises(ValueError):run_plan(old)
        for value in ([],{},None,True):
            bad=deepcopy(good);bad['steps'][0]['operations'][0]['args']['name']=value
            with self.assertRaises(ValueError):run_plan(bad)
        for value in (True,2.,1):
            bad=deepcopy(good);bad['version']=value
            with self.assertRaises(ValueError):run_plan(bad)

    def test_budget_failure_is_atomic_after_earlier_logs_and_output(self):
        source='data early;x=1;put x;run;data late;x=2;again:output;goto again;run;'
        p=compiled(source)
        with self.assertRaises(ValueError):run_plan(p)
        stream=io.StringIO();ns={}
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,ns)
        self.assertEqual(stream.getvalue(),'');self.assertNotIn('result',ns)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);sas=folder/'job.sas';sas.write_text(source)
            proc=subprocess.run([sys.executable,'-m','saschi','run',str(sas),'--output',str(folder/'out')],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(proc.returncode,0);self.assertFalse((folder/'out/result.json').exists())
            receipt=json.loads((folder/'out/receipt.json').read_text());self.assertFalse(receipt['accepted'])

    def test_no_trigger_legacy_shapes_and_CPP_refusal(self):
        for source in ('data d;stop=2;do i=1 to stop;x=i;end;run;',
                       'data _null_;put "stop; goto l; link sub; return;";run;',
                       'data d;input x;cards;\n1 goto\n;\nrun;'):
            p=compiled(source);self.assertTrue(all(s['kind']=='data' for s in p['steps']));run_plan(p)
        self.assertTrue(cpp_translate('data _null_;x=1;again:stop;run;').blocked)


    def test_complete_unchanged_external_two_steps_are_not_a_partial_claim(self):
        import os,hashlib
        corpus=Path(os.environ.get('SASCHI_ROKU_CORPUS',ROOT.parent/'saschi-roku/corpus'))
        source=(corpus/'flow_control_structures.sas').read_text()
        expected={'datasets':{},'log':[f'{n} {p} ' for p in range(1,11) for n in range(1,p+1)]+['2 15 1 ','533 221 13 ','8 44 4 ']}
        self.assertTrue(equal(execute(source),expected,ordered_maps=True))
        self.assertEqual(hashlib.sha256(''.join(x+'\n' for x in expected['log']).encode()).hexdigest(),'b9550d1174ff5ffcd7fb23a0c323a60f8d7a12ba8f06565632074fc75a19df25')

    def test_link_keeps_PDV_and_goto_preserves_caller(self):
        source='data d;x=0;link sub;put x;link sub;put x;stop;sub:goto finish;finish:x=x+1;return;run;'
        self.assertEqual(execute(source),{'datasets':{'d':{'schema':{'x':'number'},'rows':[]}},'log':['1 ','2 ']})

    def test_unlinked_RETURN_advances_INPUT_and_resets_scratch_only(self):
        source='data d;input x;if x=1 then scratch=9;total+x;return;\ncards;\n1\n2\n;\nrun;'
        self.assertEqual(execute(source)['datasets']['d']['rows'],[{'x':1.,'scratch':9.,'total':1.},{'x':2.,'scratch':None,'total':3.}])
        suppressed=source.replace('return;','if 0 then output;return;')
        self.assertEqual(execute(suppressed)['datasets']['d']['rows'],[])

    def test_STOP_with_INPUT_keeps_prior_output_and_stops_future_rows(self):
        source='data d;input x;if x=2 then stop;output;return;\ncards;\n1\n2\n3\n;\nrun;'
        self.assertEqual(execute(source)['datasets']['d']['rows'],[{'x':1.}])
        self.assertTrue(compile_plan(source.replace('3\n;','1.5\n;')).blocked)

    def test_implicit_callee_RETURN_at_step_end_resumes_caller(self):
        source='data d;input x;link sub;put x;return;sub:x=x+1;\ncards;\n1\n2\n;\nrun;'
        result=execute(source);self.assertEqual(result['log'],['2 ','3 ']);self.assertEqual(result['datasets']['d']['rows'],[{'x':2.},{'x':3.}])

    def test_RETURN_inside_loop_skips_unreached_increment_and_resumes(self):
        source='data d;x=0;link sub;output;stop;sub:do i=2147483647 to 2147483647 by 2147483647;x=x+1;return;end;run;'
        self.assertEqual(execute(source)['datasets']['d']['rows'],[{'x':1.,'i':2147483647.}])

    def test_unlinked_RETURN_without_INPUT_is_conservatively_refused(self):
        for source in ('data d;x=1;return;run;','data d;x=1;if 0 then return;stop;run;',
                       'data d;x=1;goto done;done:return;run;',
                       'data d;x=1;do while(0);return;end;stop;run;'):
            self.assertTrue(compile_plan(source).blocked,source)
        self.assertEqual(execute('data d;x=1;link sub;stop;sub:x=2;return;run;')['datasets']['d']['rows'],[])

    def test_nested_recursive_and_input_reentry_paths_refuse_statically(self):
        for source in ('data d;x=1;link a;stop;a:link a;return;run;',
                       'data d;x=1;link a;link b;stop;a:return;b:return;run;',
                       'data d;x=1;top:link a;stop;a:goto top;return;run;',
                       'data d;x=1;do;link a;end;stop;a:return;run;',
                       'data d;before:input x;goto before;\ncards;\n1\n;\nrun;'):
            self.assertTrue(compile_plan(source).blocked,source)

    def test_empty_INPUT_and_incomplete_consumed_token_validation(self):
        source='data d;input a b;link sub;return;sub:x=mod(a,b);return;\ncards;\n;\nrun;'
        self.assertEqual(execute(source)['datasets']['d']['rows'],[])
        for records in ('1.5','1e20','bad'):
            self.assertTrue(compile_plan(source.replace('\ncards;\n;','\ncards;\n'+records+'\n;')).blocked)
        self.assertTrue(compile_plan(source.replace('mod(a,b)','mod(a,0)')).blocked)

    def test_empty_and_skipped_mixed_container_depth_bounds(self):
        for prefix in ('do;','if 0 then do;'):
            for count in (32,33):
                groups=count-(1 if prefix.startswith('if') else 0)
                source='data d;x=1;'+prefix+'do;'*(groups-1)+'end;'*groups+'stop;run;'
                self.assertEqual(compile_plan(source).blocked,count==33)
        good=compiled('data d;x=1;stop;run;')
        for count in (32,33):
            node={'kind':'do_group','line':1,'args':{'body':[]}}
            for _ in range(count-1):node={'kind':'do_group','line':1,'args':{'body':[node]}}
            bad=deepcopy(good);bad['steps'][0]['operations'].insert(2,node)
            if count==33:
                with self.assertRaises(ValueError):run_plan(bad)
            else:run_plan(bad)

    def test_profile_selection_ignores_quoted_stage2_words(self):
        for literal in ('return','link sub','input x','mod(1,2)'):
            p=compiled('data d;x=1;stop;put "'+literal+'";run;')
            self.assertEqual(p['steps'][0]['operations'][0]['args'],{'name':'scalar-jump-v1'})


    def test_same_code_line_INPUT_records_start_on_following_physical_line(self):
        from examples.verify_scalar_jump import batch_witness,case,assert_tree
        source='data d;retain total 0;input x;link r;total+x;return;r:scratch=x*2;return;datalines;\n1\n3\n.\n;\nrun;'
        expected={'datasets':{'d':{'schema':dict.fromkeys(('total','x','scratch'),'number'),'rows':[{'total':1.,'x':1.,'scratch':2.},{'total':4.,'x':3.,'scratch':6.},{'total':4.,'x':None,'scratch':None}]}},'log':[]}
        assert_tree(execute(source),expected);r=batch_witness([case('same_line',source)])[0];self.assertIsNotNone(r);assert_tree(r['result'],expected)



    def test_independent_full_source_hands_and_trace_pins(self):
        from examples.verify_scalar_jump import hand_cases,batch_witness,execute as witnessed,assert_tree,assert_trace
        for mode in ('jump','link'):
            cases=hand_cases(mode);independent=batch_witness(cases)
            for case,r in zip(cases,independent):
                self.assertIsNotNone(r,case['name']);o=witnessed(case['source'],emitted=True);assert_tree(r['result'],case['expected']);assert_tree(o['result'],case['expected']);assert_trace(r['trace'],o['trace'])
                if case['trace'] is not None:assert_trace(r['trace'],case['trace'])

    def test_both_actual_CLI_whole_witnesses_and_wrong_comparators(self):
        from examples.verify_scalar_jump import ORIGINAL,original_expected,corpus_source,corpus_expected,cli_check,wrong_comparators
        cli_check(ORIGINAL.read_text(),expected=original_expected());cli_check(corpus_source().read_text(),expected=corpus_expected())
        self.assertEqual(wrong_comparators('link'),8)

    def test_exact_old_STOP_source_promotion_retains_older_boundaries(self):
        from examples.verify_scalar_jump import assert_stop_promotion
        assert_stop_promotion(self,'data d;x=1;do;stop;end;run;')

    def test_strict_portable_graph_shape_and_static_dead_INPUT(self):
        good=compiled('data d;x=1;done:stop;run;')
        for kind in ([],{},None,True):
            bad=deepcopy(good);bad['steps'][0]['operations'][1]['kind']=kind
            with self.assertRaises(ValueError):run_plan(bad)
        for alter in ('extra','labels','automatic','cyclic','deep'):
            bad=deepcopy(good);step=bad['steps'][0]
            if alter=='extra':step['unexpected']=1
            elif alter=='labels':step['operations'][2]['args']['name']='absent';step['operations'].append({'kind':'goto','line':1,'args':{'name':'done'}})
            elif alter=='automatic':step['operations'][1]['args']['name']='_n_'
            elif alter=='cyclic':step['operations'].append({'kind':'do_group','line':1,'args':{'body':step['operations']}})
            else:step['operations'].append({'kind':'put_literal','line':1,'args':{'literals':['a']*20001}})
            with self.assertRaises(ValueError):run_plan(bad)

    def test_expanded_operation_1024_and_local_label_64_boundaries(self):
        for count in (1022,1023):
            source='data d;x=1;'+'x=1;'*count+'stop;run;'
            self.assertEqual(compile_plan(source).blocked,count==1023)
        for count in (64,65):
            source='data d;x=1;'+''.join(f'l{i}:x=1;' for i in range(count))+'stop;run;'
            self.assertEqual(compile_plan(source).blocked,count==65)

    def test_instruction_budget_exact_100000_and_next_dispatch_refusal(self):
        from examples.verify_scalar_jump import batch_witness,case,assert_tree
        source='data d;n=0;x=0;y=0;again:n=n+1;if n<24999 then goto again;stop;run;'
        expected={'datasets':{'d':{'schema':dict.fromkeys(('n','x','y'),'number'),'rows':[]}},'log':[]}
        assert_tree(execute(source),expected)
        bad=source.replace('24999','25000')
        with self.assertRaises(ValueError):execute(bad)
        results=batch_witness([case('exact',source),case('exceeded',bad)])
        self.assertIsNotNone(results[0]);assert_tree(results[0]['result'],expected);self.assertIsNone(results[1])

    def test_loop_reservation_budget_stays_independent_of_GOTO_budget(self):
        from examples.verify_scalar_jump import batch_witness,case
        source='data d;n=0;again:do i=1 to 6000;leave;end;n=n+1;if n<2 then goto again;stop;run;'
        self.assertFalse(compile_plan(source).blocked)
        with self.assertRaises(ValueError):execute(source)
        self.assertEqual(batch_witness([case('reserve',source)]),[None])

    def test_large_accepted_legacy_plan_has_no_new_scan_limit(self):
        good=compiled('data d;x=1;run;');assignment=deepcopy(good['steps'][0]['operations'][0]);good['steps'][0]['operations']=[deepcopy(assignment) for _ in range(20001)];before=deepcopy(good)
        self.assertEqual(run_plan(good)['datasets']['d']['rows'],[{'x':1.}]);self.assertEqual(good,before)


    def test_ordinary_keyword_targets_match_source_and_portable_state(self):
        from examples.verify_scalar_jump import batch_witness,case,assert_tree
        for name in ('set','keep','drop','input','file','retain','stop','return','link','goto'):
            source=f'data d;{name}=1;output;stop;run;';expected={'datasets':{'d':{'schema':{name:'number'},'rows':[{name:1.}]}},'log':[]}
            assert_tree(execute(source),expected);r=batch_witness([case('ordinary',source)])[0];self.assertIsNotNone(r);assert_tree(r['result'],expected)


    def test_unrelated_generic_catalog_is_preserved_without_domain_widening(self):
        from examples.verify_scalar_jump import execute as witnessed,batch_witness,case,assert_tree
        catalog={'RAW':{'encoding':'latin-1','label':'unrelated','schema':{'Fraction':'number','Tag':'number','Text':{'type':'character','length':1,'label':'','format':''}},'rows':[{'Fraction':.1,'Tag':{'missing':'A'},'Text':'é'}]}}
        before=deepcopy(catalog);source='data d;x=1;output;stop;run;';o=witnessed(source,catalog,emitted=True);r=batch_witness([case('generic',source,catalog=catalog)])[0];self.assertIsNotNone(r);assert_tree(o['result'],r['result']);self.assertEqual(catalog,before)



    def test_exchange_and_flow_keep_exact_state_in_both_step_orders(self):
        export_source='data _null_;\ninfile datalines dlm=\',\' firstobs=2;\nfile "pair.csv" dlm=\',\';\ninput v1-v3;\ntotal=sum(of v1-v3);\nput v1-v3 total;\ndatalines;\nV1,V2,V3\n2,4,8\n3,6,9\n;\nrun;\n'
        flow_source='data audit;\nretain total 0;\ninput x;\nlink scale;\ntotal+scratch;\noutput;\nreturn;\nscale:scratch=x*2;\nreturn;\ndatalines;\n2\n3\n;\nrun;\n'
        expected={'datasets':{'audit':{'schema':{'total':'number','x':'number','scratch':'number'},'rows':[{'total':4.,'x':2.,'scratch':4.},{'total':10.,'x':3.,'scratch':6.}]}},'log':[],'exports':{'pair.csv':'2,4,8,14\n3,6,9,18\n'}}
        for source,kinds,input_lines,data_lines,infile_line in (
            (export_source+flow_source,['exchange_data','flow_data'],[4,15],[8,23],2),
            (flow_source+export_source,['flow_data','exchange_data'],[3,18],[11,22],16)):
            with self.subTest(kinds=kinds):
                plan=compiled(source)
                self.assertEqual([s['kind'] for s in plan['steps']],kinds)
                reads=[next(o for o in s['operations'] if o['kind'] in ('exchange_input','input_list')) for s in plan['steps']]
                self.assertEqual([o['line'] for o in reads],input_lines)
                self.assertEqual([o['args']['data_line'] for o in reads],data_lines)
                exchange=next(o for o in reads if o['kind']=='exchange_input')
                self.assertEqual(exchange['args']['infile_line'],infile_line)
                self.assertTrue(equal(run_plan(plan),expected,ordered_maps=True))
                stream=io.StringIO();namespace={}
                with contextlib.redirect_stdout(stream):exec(translate(source).code,namespace)
                self.assertEqual(stream.getvalue(),'')
                self.assertTrue(equal(namespace['result'],expected,ordered_maps=True))

    def test_intervening_flow_preserves_one_FILE_compile_and_runtime_limits(self):
        export_source='data _null_;\ninfile datalines dlm=\',\' firstobs=2;\nfile "pair.csv" dlm=\',\';\ninput v1-v3;\ntotal=sum(of v1-v3);\nput v1-v3 total;\ndatalines;\nV1,V2,V3\n2,4,8\n3,6,9\n;\nrun;\n'
        flow_source='data audit;\nretain total 0;\ninput x;\nlink scale;\ntotal+scratch;\noutput;\nreturn;\nscale:scratch=x*2;\nreturn;\ndatalines;\n2\n3\n;\nrun;\n'
        second=export_source.replace('pair.csv','other.csv')
        for source,line in ((export_source+flow_source+second,29),
                            (export_source+flow_source+export_source,29),
                            (flow_source+export_source+second,29),
                            (export_source+second+flow_source,15)):
            with self.subTest(line=line,source=source):
                plan=compile_plan(source)
                self.assertEqual([(t.line,t.statement,t.construct,t.reason) for t in plan.tickets],
                    [(line,'FILE','csv-export','one export destination per program is the bounded profile')])
                forced=plan.to_dict();forced['tickets']=[]
                with self.assertRaises(ValueError):run_plan(forced)


if __name__=='__main__':unittest.main()
