"""Strict new procedure shapes, source/state boundaries and complete witnesses."""
from copy import deepcopy
import contextlib
import io
import unittest

from .procedures import validate_step,validate_program,execute_means,execute_print,MEANS_PROFILE,PRINT_PROFILE
from .plan import compile_plan,_compile_before_procedures
from .runtime import run_plan
from .emit_py import translate
from .emit_cpp import translate as cpp_translate
from .compare import equal
from .rules import route_statement
from examples.verify_means_output import (ORIGINAL,REPORT,SUMMARY_NAMES,incoming,plain,
    original_expected,original_trace,execute,program_witness,means_source,print_source,
    hand_cases,refusal_cases,batch_witness,check_original)


class ProcedureTests(unittest.TestCase):
    def plan(self,source):
        parsed=compile_plan(source);self.assertFalse(parsed.blocked,parsed.tickets);return parsed.to_dict()

    def test_original_source_result_report_trace_and_CLI_pins(self):
        check_original()

    def test_independent_R_hand_extremes_missing_and_metadata(self):
        cases=hand_cases('means')[:-1]+hand_cases('print')[:-1]
        witnesses=batch_witness([(s,c) for _,s,c in cases])
        for (name,source,catalog),witness in zip(cases,witnesses,strict=True):
            with self.subTest(name=name):
                self.assertIsNotNone(witness);actual=execute(source,catalog,True)
                self.assertTrue(equal(actual['result'],witness['result'],ordered_maps=True));self.assertEqual(actual['trace'],witness['trace'])

    def test_empty_schema_and_header_are_materialized(self):
        out=execute(means_source(sort=True,printed=True),incoming(False))['result']
        self.assertEqual(out['datasets']['summary']['rows'],[])
        self.assertEqual(list(out['datasets']['summary']['schema']),SUMMARY_NAMES)
        self.assertEqual(out['reports'],{'print.txt':REPORT.splitlines()[0]+'\n'})

    def test_BY_metadata_clones_and_NO_INHERIT_is_fresh(self):
        catalog=incoming();before=deepcopy(catalog);out=execute(ORIGINAL.read_text(),catalog)['result'];schema=out['datasets']['summary']['schema']
        self.assertEqual(schema['g'],catalog['raw']['schema']['g'])
        for name in SUMMARY_NAMES[1:]:self.assertEqual(schema[name],{'type':'number','length':8})
        self.assertEqual(set(out['datasets']['summary']),{'schema','rows'})
        schema['g']['label']='mutated';schema['avg']['length']=4;self.assertEqual(catalog,before)

    def test_missing_BY_FREQ_N_NMISS_and_singleton_variance(self):
        summary=execute(ORIGINAL.read_text(),incoming())['result']['datasets']['summary']['rows']
        self.assertIsNone(summary[0]['g']);self.assertEqual(summary[2]['_freq_'],2)
        self.assertEqual(summary[2]['nobs'],1);self.assertEqual(summary[2]['nmissing'],1)
        self.assertIsNone(summary[2]['variance']);self.assertEqual(summary[4]['nobs'],0)
        self.assertIsNone(summary[4]['avg']);self.assertIsNone(summary[4]['variance'])

    def test_exact_sufficient_statistics_and_DF(self):
        for rows,wanted in [([(0,-1000),(0,1000)],2000000),([(0,999),(0,1000)],0.5),([(0,1),(0,3),(0,5)],4)]:
            observed=execute(means_source(),plain(rows))['result']['datasets']['summary']['rows'][0]
            self.assertEqual(observed['variance'],wanted)

    def test_alias_order_and_namespaces_are_source_ordered(self):
        source=means_source(stats='var=variance mean=avg nmiss=nmissing n=nobs')
        observed=execute(source,plain([(1,1),(1,3)]))['result']['datasets']['summary']
        self.assertEqual(list(observed['schema']),['g','_type_','_freq_','variance','avg','nmissing','nobs'])
        self.assertEqual(list(observed['rows'][0]),list(observed['schema']))

    def test_all_selected_descriptors_validate_when_empty(self):
        for kind in ('means','print'):
            source=means_source() if kind=='means' else print_source()
            for spec in ({'type':'character','length':1},{'type':'number','length':4},{'type':'number','format':'8.'}):
                with self.subTest(kind=kind,spec=spec),self.assertRaises(ValueError):
                    run_plan(self.plan(source),{'raw':{'schema':{'g':'number','x':spec},'rows':[]}})

    def test_selected_values_validate_eagerly_and_remain_bounded(self):
        for name in ('g','x'):
            for value in (True,{'missing':'A'},1.5,1001,float('inf')):
                catalog=plain([(0,1),(0,3)]);catalog['raw']['rows'][-1][name]=value
                with self.subTest(name=name,value=value),self.assertRaises(ValueError):run_plan(self.plan(means_source()),catalog)

    def test_unsorted_input_refuses_and_SORT_reuses_stability(self):
        with self.assertRaisesRegex(ValueError,'ascending BY'):run_plan(self.plan(means_source()),plain([(1,1),(0,2)]))
        actual=execute(ORIGINAL.read_text(),incoming())['result']
        self.assertEqual([row['id'] for row in actual['datasets']['ordered']['rows']],[4,10,2,6,12,1,7,5,8,3,9,11])

    def test_existing_destination_even_empty_refuses(self):
        plan=self.plan(means_source());catalog=plain([]);catalog['summary']={'schema':{},'rows':[]};before=deepcopy(catalog)
        with self.assertRaisesRegex(ValueError,'existing destination'):run_plan(plan,catalog)
        self.assertEqual(catalog,before)

    def test_alias_collisions_static_even_empty_and_portable(self):
        for alias in ('g','_type_','_freq_','nmissing'):
            source=means_source().replace('n=nobs','n='+alias)
            self.assertTrue(compile_plan(source).blocked)
            step=self.plan(means_source())['steps'][0];step['operations'][0]['args']['statistics'][0]['name']=alias
            with self.assertRaises(ValueError):validate_step(step)

    def test_every_new_statement_requires_its_semicolon(self):
        for source in (means_source(),print_source()):
            positions=[i for i,c in enumerate(source) if c==';']
            for i in positions:
                bad=source[:i]+source[i+1:]
                with self.subTest(source=bad):self.assertTrue(compile_plan(bad).blocked)
            self.assertIsNone(batch_witness([(source[:-1],plain([]))])[0])

    def test_new_steps_are_exact_version_two_and_defaults(self):
        for source in (means_source(),print_source()):
            base=self.plan(source)['steps'][0]
            for version in (1,3,True,False,2.,'2',None):
                with self.assertRaises(ValueError):validate_step(base,version)
            for key,value in [('kind','data'),('name','UPPER'),('line',False),('inputs',()),('by',()),('nodupkey',True),('where',{}),('retained',[]),('lengths',{'x':8}),('display_names',{'x':'X'}),('extra',1)]:
                step=deepcopy(base);step[key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):validate_step(step)
            for key in base:
                step=deepcopy(base);del step[key]
                with self.assertRaises(ValueError):validate_step(step)

    def test_operation_profile_shape_and_line_strictness(self):
        for source in (means_source(),print_source()):
            base=self.plan(source)['steps'][0]
            for value in ([],(),[{}],[base['operations'][0]]*2):
                step=deepcopy(base);step['operations']=value
                with self.assertRaises(ValueError):validate_step(step)
            for key,value in [('kind',[]),('line',True),('line',0),('args',{}),('extra',1)]:
                step=deepcopy(base);step['operations'][0][key]=value
                with self.assertRaises(ValueError):validate_step(step)
            for value in ([False,1], [0,1], ['1','2'], [], [2,1]):
                step=deepcopy(base);step['operations'][0]['args']['source_lines']=value
                with self.assertRaises(ValueError):validate_step(step)
            step=deepcopy(base);step['operations'][0]['args']['profile']='binary64-v1'
            with self.assertRaises(ValueError):validate_step(step)

    def test_malformed_stats_names_and_cycles_refuse(self):
        base=self.plan(means_source())['steps'][0]
        for value in ([],(),[{}]*4,[{'statistic':[],'name':'n'}]*4,[{'statistic':'n','name':'n'}]*4):
            step=deepcopy(base);step['operations'][0]['args']['statistics']=value
            with self.assertRaises(ValueError):validate_step(step)
        step=self.plan(print_source())['steps'][0];step['operations'][0]['args']['names'].append(step)
        with self.assertRaises(ValueError):validate_step(step)
        plan=self.plan('data d;x=1;run;');plan['steps'][0]['operations'].append(plan['steps'][0])
        with self.assertRaises(ValueError):run_plan(plan)

    def test_old_kinds_and_numeric_markers_refuse_hidden_new_operations(self):
        new=self.plan(print_source())['steps'][0]['operations'][0]
        for marker in (None,'binary64-v1','binary64-rows-v1','binary64-pipeline-v1'):
            plan=self.plan('data d;x=1;run;');plan['steps'][0]['operations'].append(deepcopy(new))
            if marker:plan['steps'][0]['operations'].insert(0,{'kind':'numeric_profile','line':1,'args':{'name':marker}})
            with self.assertRaises(ValueError):run_plan(plan)

    def test_global_one_PRINT_across_flow_and_exchange_wrappers(self):
        printed=print_source();middle=['proc sort data=raw out=ordered;by g;run;',
            'data _null_;x=1;stop;run;',
            "data _null_;file 'x.csv' dlm=',';x=1;put x;run;"]
        for source in middle:
            combined=printed+source+printed;self.assertTrue(compile_plan(combined).blocked)
        plan=self.plan(printed);plan['steps'].append(deepcopy(plan['steps'][0]))
        with self.assertRaisesRegex(ValueError,'one PRINT'):run_plan(plan,plain([(0,1)]))

    def test_global_one_FILE_across_procedure_boundaries_and_ticket_dedup(self):
        file="data _null_;file 'x.csv' dlm=',';x=1;put x;run;"
        for source in (file+print_source()+file,file+file+print_source()):
            parsed=compile_plan(source);self.assertTrue(parsed.blocked)
            matches=[t for t in parsed.tickets if t.reason=='one export destination per program is the bounded profile']
            self.assertEqual(len(matches),1)

    def test_PRINT_numeric_domain_midpoint_and_column_bounds(self):
        for value in (0.00001,0.12345678905,2147483648,{'missing':'A'}):
            with self.subTest(value=value),self.assertRaises(ValueError):run_plan(self.plan(print_source()),{'raw':{'schema':{'x':'number'},'rows':[{'x':value}]}})
        for n in (0,33):self.assertTrue(compile_plan(print_source(' '.join(f'x{i}' for i in range(n)))).blocked)

    def test_independent_R_exact_midpoint_boundary_matches_hand_rational_distance(self):
        import math
        from fractions import Fraction
        cases=[];wanted=[]
        for center,places in [(0.12345678905,10),(-0.1234567895,9),(1234.12345675,7)]:
            midpoint=Fraction(round(center*10**places-0.5)*2+1,2*10**places)
            for distance in range(-18,19):
                value=center
                for _ in range(abs(distance)):value=math.nextafter(value,math.inf if distance>0 else -math.inf)
                accepted=abs(Fraction(value)-midpoint)>16*Fraction(math.ulp(value))
                cases.append((print_source(),{'raw':{'schema':{'x':'number'},'rows':[{'x':value}]}}));wanted.append(accepted)
        witnesses=batch_witness(cases)
        for (source,catalog),accepted,witness in zip(cases,wanted,witnesses,strict=True):
            with self.subTest(value=catalog['raw']['rows'][0]['x']):
                self.assertEqual(witness is not None,accepted)
                if accepted:self.assertTrue(equal(execute(source,catalog)['result'],witness['result'],ordered_maps=True))
                else:
                    with self.assertRaises(ValueError):run_plan(self.plan(source),catalog)

    def test_exact_maximum_report_and_independent_R(self):
        _,source,catalog=hand_cases('print')[-1];actual=execute(source,catalog,True)['result'];text=actual['reports']['print.txt']
        self.assertEqual(len(text),417056);records=text.splitlines();self.assertEqual(len(records),1001);self.assertEqual(len(records[0]),1055);self.assertTrue(all(len(row)==415 for row in records[1:]))
        witness=batch_witness([(source,catalog)])[0];self.assertIsNotNone(witness);self.assertTrue(equal(actual,witness['result'],ordered_maps=True))

    def test_1000_rows_accept_and_1001_refuse_independent_of_group_count(self):
        for count in (1000,1001):
            catalog=plain([(0,1)]*count)
            if count==1000:self.assertEqual(execute(means_source(),catalog)['result']['datasets']['summary']['rows'][0]['_freq_'],1000)
            else:
                for source in (means_source(),print_source()):
                    with self.assertRaisesRegex(ValueError,'1000'):run_plan(self.plan(source),catalog)

    def test_public_helpers_and_runtime_preserve_inputs_plans_and_generics(self):
        catalog=hand_cases('print')[-2][2];before=deepcopy(catalog);plan=self.plan(print_source());saved=deepcopy(plan)
        out=run_plan(plan,catalog);self.assertTrue(equal(plan,saved,ordered_maps=True));self.assertTrue(equal(catalog,before,ordered_maps=True))
        self.assertEqual(out['datasets']['other']['rows'][0]['fraction'],0.1);self.assertEqual(out['datasets']['other']['rows'][0]['tag'],{'missing':'A'});self.assertEqual(out['datasets']['other']['rows'][0]['c'],'é')

    def test_source_lines_comments_case_and_normalized_names(self):
        source='/* first */\n\nPROC MEANS DATA=RAW NOPRINT VARDEF=DF;\n BY G; VAR X;\n OUTPUT OUT=SUMMARY N=NOBS NMISS=NMISSING MEAN=AVG VAR=VARIANCE / NOINHERIT;\n RUN;'
        plan=self.plan(source);step=plan['steps'][0];self.assertEqual(step['line'],3);self.assertEqual(step['operations'][0]['args']['source_lines'],[4,4,5,6])
        self.assertEqual(step['name'],'summary');self.assertEqual(step['inputs'],['raw'])

    def test_no_trigger_legacy_shapes_literals_and_opaque_records_unchanged(self):
        sources=["data _null_;put 'proc print data=raw noobs;';run;",'data d;means=1;print=2;run;',"data d;input x;datalines;\n1\n;\nrun;",'proc sort data=raw out=ordered nodupkey;by g;run;']
        for source in sources:self.assertEqual(compile_plan(source).to_dict(),_compile_before_procedures(source).to_dict())
        self.assertTrue(compile_plan('proc sort data=raw out=ordered;by descending g;run;').blocked)

    def test_large_old_chunk_keeps_legacy_budget_and_final_PRINT(self):
        source='data many;'+''.join(f'x{i}={i};' for i in range(20001))+'run;'+print_source('x0',input='many')
        plan=self.plan(source);out=run_plan(plan);self.assertEqual(len(out['datasets']['many']['schema']),20001);self.assertEqual(out['reports'],{'print.txt':'x0\n0\n'})

    def test_CPP_refuses_whole_new_procedure_program(self):
        for source in (means_source(),print_source(),ORIGINAL.read_text()):self.assertTrue(cpp_translate(source).blocked)

    def test_late_failure_has_no_emitted_stdout_or_result(self):
        source=ORIGINAL.read_text()+'data bad;zero=0;y=1/zero;run;';generated=translate(source);self.assertFalse(generated.blocked)
        stream=io.StringIO();namespace={'inputs':incoming()}
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(generated.code,namespace)
        self.assertEqual(stream.getvalue(),'');self.assertNotIn('result',namespace)

    def test_shared_refusals_run_on_source_and_independent_R(self):
        cases=refusal_cases('means')+refusal_cases('print');witnesses=batch_witness([(source,catalog) for _,source,catalog in cases])
        for (name,source,catalog),witness in zip(cases,witnesses,strict=True):
            with self.subTest(name=name):
                self.assertIsNone(witness)
                plan=compile_plan(source)
                if not plan.blocked:
                    with self.assertRaises((ValueError,TypeError,KeyError)):run_plan(plan.to_dict(),catalog)

    def test_catalog_contexts_classify_source_without_Plan_dependence(self):
        from .catalog import record_pass
        source=ORIGINAL.read_text();cat,c=record_pass(source,compile_plan(source),git='test')
        try:
            rows=cat._con.execute('SELECT construct,rule_id FROM statements ORDER BY rowid').fetchall()
            self.assertEqual(rows[3:8],[('proc-means','ST-017')]*5)
            self.assertEqual(rows[8:],[('proc-print','ST-018')]*3)
            self.assertEqual(c.n_statements,11)
        finally:cat.close()
        self.assertEqual(route_statement('var x'),('unknown',''))
        self.assertEqual(route_statement('output out=s n=n /noinherit'),('unknown',''))

    def test_catalog_context_resets_and_opaque_words_do_not_select_it(self):
        from .catalog import record_pass
        source='proc means data=raw noprint vardef=df;by g;var x;proc bogus;var x;run;data d;input x;datalines;\nproc print data=raw noobs\n;\nrun;var x;'
        cat,_=record_pass(source,compile_plan(source),git='test')
        try:
            rows=cat._con.execute('SELECT statement,construct FROM statements ORDER BY rowid').fetchall()
            self.assertEqual(rows[4][1],'unknown');self.assertEqual(rows[-1][1],'unknown')
            self.assertTrue(all(construct!='proc-print' for statement,construct in rows if statement.startswith('proc print')))
        finally:cat.close()
        self.assertEqual(route_statement('proc means data=raw noprint;'),('stat-means','ST-001'))
        for header,construct in [('proc print data=raw noobs;', 'proc-print'),
                                 ('proc means data=raw noprint vardef=df;', 'proc-means')]:
            for boundary in ('proc;', 'data;', 'PROC;', 'DATA;'):
                source=header+boundary+'var x;run;'
                self.assertTrue(compile_plan(source).blocked)
                cat,_=record_pass(source,compile_plan(source),git='test')
                try:
                    rows=cat._con.execute('SELECT construct,rule_id FROM statements ORDER BY rowid').fetchall()
                    self.assertEqual(rows[-2:],[('unknown',''),('unknown','')])
                finally:cat.close()
            for assignment in ('data=1;', 'proc=1;', 'data = 1;', 'proc = 1;'):
                source=header+assignment+'var x;run;'
                cat,_=record_pass(source,compile_plan(source),git='test')
                try:
                    rows=cat._con.execute('SELECT construct FROM statements ORDER BY rowid').fetchall()
                    self.assertEqual(rows[-2:],[(construct,),(construct,)])
                finally:cat.close()

    def test_new_routing_preserves_old_statistics_and_SORT(self):
        self.assertEqual(route_statement('proc means data=raw noprint vardef=df;'),('proc-means','ST-017'))
        self.assertEqual(route_statement('proc print data=summary noobs;'),('proc-print','ST-018'))
        self.assertEqual(route_statement('proc means data=raw;'),('stat-means','ST-001'))
        self.assertEqual(route_statement('proc sort data=raw;'),('sort','DS-008'))


if __name__=='__main__':unittest.main()
