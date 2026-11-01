"""New mixed report/title shape,state,domain and compatibility boundaries."""
from copy import deepcopy
from dataclasses import asdict
import unittest

from .plan import Step,Operation
from .mixed_reports import (PRINT_PROFILE,TITLE_PROFILE,validate_step,validate_program,
    execute_title,execute_print,validate_reports,refuse_legacy,parse_title,parse_print)
from .parser import split_statements


def title_step(value=None):
    return asdict(Step('report_title','_null_',1,operations=[Operation('report_title',1,{'profile':TITLE_PROFILE,'text':value})]))


def print_step(name='raw'):
    return asdict(Step('mixed_print',name,1,inputs=[name],operations=[Operation('mixed_print',1,{'profile':PRINT_PROFILE,'source_lines':[1]})]))


def table(rows=None):
    return {'schema':{'word':{'type':'character','length':4},'n':{'type':'number','length':8}},
            'rows':[{'word':' a  ','n':-2.0},{'word':'    ','n':None}] if rows is None else rows}


class MixedReportTests(unittest.TestCase):
    def test_title_set_reset_and_outer_spaces(self):
        events=[]
        self.assertIsNone(execute_title(title_step(),trace=events))
        self.assertEqual(execute_title(title_step('  hello  '),trace=events),'  hello  ')
        self.assertEqual(events,['title|reset','title|set|'+'  hello  '.encode().hex()])

    def test_title_domain_macro_and_empty_refusals(self):
        for value in ('',' ','\t','\n','é','x'*129,'a&b','x%y',1,False,[],{}):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_step(title_step(value))
        self.assertEqual(execute_title(title_step('x'*128)),'x'*128)

    def test_mixed_text_quotes_padding_numbers_and_obs(self):
        catalog={'raw':table()};before=deepcopy(catalog)
        expected='TITLE:   hello  \nobs word n\n1 " a" -2\n2 "" .\n'
        self.assertEqual(execute_print(print_step(),catalog,'  hello  '),{'print_01.txt':expected})
        self.assertEqual(catalog,before)
        self.assertEqual(execute_print(print_step(),catalog,ordinal=2)['print_02.txt'].splitlines()[1],'1 " a" -2')

    def test_JSON_backslash_and_quote_escape_in_renderer(self):
        raw=table([{'word':'a\\b ','n':0.0},{'word':'x"y ','n':2147483647.0}])
        rendered=execute_print(print_step(),{'raw':raw})['print_01.txt']
        self.assertIn('1 "a\\\\b" 0\n',rendered)
        self.assertIn('2 "x\\"y" 2147483647\n',rendered)

    def test_empty_table_still_has_title_and_header(self):
        self.assertEqual(execute_print(print_step(),{'raw':table([])},'empty'),{'print_01.txt':'TITLE: empty\nobs word n\n'})

    def test_cell_domains_validate_before_coercion(self):
        for value in (True,False,{'missing':'A'},0.5,float('nan'),float('inf'),2147483648,-2147483648,10**1000,'1'):
            raw=table([{'word':'good','n':value}])
            with self.subTest(value=value),self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})
        for value in (None,False,'é   ','a\tb ','a\nb ','x','x'*5):
            raw=table([{'word':value,'n':1}])
            with self.subTest(value=value),self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})

    def test_descriptor_guards_apply_even_empty(self):
        for name,spec in [('word',{'type':'character','length':0}),('word',{'type':'character','length':65}),
                          ('word',{'type':'character','length':True}),('word',{'type':'character','length':4,'label':''}),
                          ('word',{'type':'character','length':4,'format':''}),('n','number'),
                          ('n',{'type':'number','length':4}),('n',{'type':'number','length':8,'format':'8.'})]:
            raw=table([]);raw['schema'][name]=spec
            with self.subTest(name=name,spec=spec),self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})
        for name in ('obs','WORD','K','_n_'):
            raw=table([]);raw['schema']={name:raw['schema']['word'],'n':raw['schema']['n']}
            with self.subTest(name=name),self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})

    def test_version_shape_and_unrelated_fields(self):
        for step in (title_step('ok'),print_step()):
            for version in (1,3,True,False,2.0,'2',None):
                with self.assertRaises(ValueError):validate_step(step,version)
            for key in list(step):
                bad=deepcopy(step);del bad[key]
                with self.subTest(key=key),self.assertRaises(ValueError):validate_step(bad)
            for key,value in [('line',True),('kind',[]),('by',['x']),('nodupkey',0),('where',{}),('lengths',{'x':8}),('display_names',{'x':'X'}),('extra',1)]:
                bad=deepcopy(step);bad[key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):validate_step(bad)

    def test_exact_operation_profiles_no_presentation_knobs(self):
        for step in (title_step('ok'),print_step()):
            for key,value in [('profile','numeric-print-v1'),('ordinal',1),('basename','print.txt'),('names',['word']),('extra',1)]:
                bad=deepcopy(step);bad['operations'][0]['args'][key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):validate_step(bad)
            for badop in ({},[],{'kind':[],'line':1,'args':{}},dict(step['operations'][0],line=False)):
                bad=deepcopy(step);bad['operations']=[badop]
                with self.assertRaises(ValueError):validate_step(bad)
        for lines in ([],[0],[True],[1,2],(1,)):
            bad=print_step();bad['operations'][0]['args']['source_lines']=lines
            with self.assertRaises(ValueError):validate_step(bad)

    def test_runtime_ordinal_and_title_strictness(self):
        for ordinal in (0,3,True,1.0,'1',None):
            with self.assertRaises(ValueError):execute_print(print_step(),{'raw':table()},ordinal=ordinal)
        with self.assertRaises(ValueError):execute_print(print_step(),{'raw':table()},title='&x')

    def test_hidden_new_operations_cycles_and_large_legacy_tree(self):
        for kind in ('report_title','mixed_print'):
            for wrapper in ('body','operation','otherwise','metadata'):
                value={'kind':'legacy','args':{wrapper:{'kind':kind}}}
                with self.subTest(kind=kind,wrapper=wrapper),self.assertRaises(ValueError):refuse_legacy(value)
        cyclic=[];cyclic.append(cyclic)
        with self.assertRaises(ValueError):refuse_legacy(cyclic)
        refuse_legacy([{'kind':'assign','args':{'value':i}} for i in range(20001)])
        refuse_legacy({'kind':[],'args':{}})
        refuse_legacy({'kind':'literal','value':'mixed_print logical-title-v1'})
        with self.assertRaises(ValueError):refuse_legacy({'kind':'assign','args':{'profile':TITLE_PROFILE}})

    def test_report_bundle_names_order_and_old_numeric_map(self):
        one=execute_print(print_step(),{'raw':table()})
        two={**one,**execute_print(print_step(),{'raw':table()},ordinal=2)}
        self.assertEqual(validate_reports(two),two)
        for bad in ({},{'print.txt':'obs word\n'},{'print_02.txt':one['print_01.txt']},dict(reversed(list(two.items()))),{'../x.txt':'x\n'}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_reports(bad)

    def test_resource_row_header_count_and_aggregate_caps(self):
        raw=table([{'word':'x   ','n':1.0} for _ in range(1000)])
        self.assertEqual(execute_print(print_step(),{'raw':raw})['print_01.txt'].count('\n'),1001)
        raw['rows'].append({'word':'x   ','n':1})
        with self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})
        raw={'schema':{'x'+str(i):{'type':'character','length':64} for i in range(7)},'rows':[]}
        raw['rows']=[dict.fromkeys(raw['schema'],'x'*64)]
        with self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})
        raw={'schema':{('x'+str(i)).ljust(32,'x'):{'type':'character','length':1} for i in range(32)},'rows':[]}
        with self.assertRaises(ValueError):execute_print(print_step(),{'raw':raw})

    def test_source_statement_full_consumption(self):
        for text in ("title 'hello';","title;","title 'x''y';"):
            validate_step(asdict(parse_title(split_statements(text)[0])))
        for text in ("title '';","title ' ';","title 'x' 'y';","title x;","title2 'x';","title '&x';","title '%x';","title 'x'"):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_title(split_statements(text)[0])
        validate_step(asdict(parse_print(split_statements('proc print data=RAW;run;'))))
        for text in ('proc print data=raw;run','proc print data=raw noobs;run;','proc print;run;',
                     'proc print data=raw;var word;run;','proc print data=K;run;','proc print data=raw(obs=1);run;'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_print(split_statements(text))


    def test_original_full_source_R_runtime_emitted_and_actual_CLI(self):
        from examples.verify_mixed_print import check_original,cli_check,data_source,original_expected
        check_original()
        late=data_source()+'proc print data=raw;run;'+data_source(['x,A,1.5'],name='late')+'proc print data=late;run;'
        receipt=cli_check(late,original_expected(),original_expected()['reports'],1)
        self.assertIn('bounded exact integers',receipt['error'])

    def test_source_generated_title_and_report_schedules(self):
        from examples.verify_mixed_print import hand_cases,batch_witness,execute,assert_tree
        for mode in ('print','title'):
            cases=hand_cases(mode)
            witnesses=batch_witness([source for _,source in cases],mode)
            for (name,source),witness in zip(cases,witnesses,strict=True):
                with self.subTest(mode=mode,name=name):
                    self.assertIsNotNone(witness);actual=execute(source,True)
                    assert_tree(actual['result'],witness['result']);self.assertEqual(actual['trace'],witness['trace'])

        from examples.verify_mixed_print import data_source
        inplace=data_source()+'proc print data=raw;run;proc sort data=raw;by word code;run;proc print data=raw;run;'
        witness=batch_witness([inplace])[0];actual=execute(inplace,True)
        assert_tree(actual['result'],witness['result']);self.assertEqual(actual['trace'],witness['trace'])
        self.assertIn('1 "beta" "B" 2',actual['result']['reports']['print_01.txt'])
        self.assertIn('1 "alpha" "A" 1',actual['result']['reports']['print_02.txt'])

    def test_shared_source_refusals_are_independent_R_boundaries(self):
        from examples.verify_mixed_print import refusal_cases,batch_witness,execute
        for mode in ('print','title'):
            cases=refusal_cases(mode);witnesses=batch_witness([source for _,source in cases],mode)
            for (name,source),witness in zip(cases,witnesses,strict=True):
                with self.subTest(mode=mode,name=name):
                    self.assertIsNone(witness)
                    with self.assertRaises((ValueError,RuntimeError)):execute(source)

    def test_new_program_title_print_and_top_level_limits(self):
        from examples.verify_mixed_print import ORIGINAL
        from .plan import compile_plan
        base=compile_plan(ORIGINAL.read_text()).to_dict()
        self.assertFalse(base['tickets']);self.assertEqual(validate_program(base)['prints'],2)
        bad=deepcopy(base);bad['steps'].append(deepcopy(next(x for x in base['steps'] if x['kind']=='mixed_print')))
        with self.assertRaises(ValueError):validate_program(bad)
        for extra,accepted in ((28,True),(29,False)):
            candidate=deepcopy(base);candidate['steps'].extend(title_step() for _ in range(extra))
            if accepted:self.assertEqual(validate_program(candidate)['titles'],32)
            else:
                with self.assertRaises(ValueError):validate_program(candidate)
        sorted_step=next(x for x in base['steps'] if x['kind']=='sort')
        for extra,accepted in ((56,True),(57,False)):
            candidate=deepcopy(base);candidate['steps'].extend(deepcopy(sorted_step) for _ in range(extra))
            if accepted:validate_program(candidate)
            else:
                with self.assertRaises(ValueError):validate_program(candidate)

    def test_input_only_program_guards_precede_catalog_normalization(self):
        from examples.verify_mixed_print import data_source
        from .plan import compile_plan
        from .runtime import run_plan
        plan=compile_plan(data_source()).to_dict();self.assertEqual(validate_program(plan)['prints'],0)
        for catalog in ({'raw':table([])},{'raw':table([{'word':'good','n':True}])},[],False):
            with self.subTest(catalog=catalog),self.assertRaises(ValueError):run_plan(deepcopy(plan),catalog)
        candidate=deepcopy(plan);candidate['steps'].append(asdict(Step('data','x',1)))
        with self.assertRaises(ValueError):validate_program(candidate)

    def test_lineage_descriptor_and_ordinary_obs_names_remain_separate(self):
        from examples.verify_mixed_print import ORIGINAL,data_source
        from .plan import compile_plan
        base=compile_plan(ORIGINAL.read_text()).to_dict()
        bad=deepcopy(base);bad['steps'][0],bad['steps'][2]=bad['steps'][2],bad['steps'][0]
        with self.assertRaises(ValueError):validate_program(bad)
        plain=data_source([],columns='obs :$1. n')
        self.assertFalse(compile_plan(plain).blocked)
        self.assertTrue(compile_plan(plain+'proc print data=raw;run;').blocked)
        for value in ('',8.,True,0):
            bad=deepcopy(base);bad['steps'][0]['operations'][0]['args']['columns'][0]['length']=value
            with self.subTest(value=value),self.assertRaises(ValueError):validate_program(bad)

    def test_old_numeric_programs_and_old_marker_shapes_stay_refused(self):
        from examples.verify_mixed_print import ORIGINAL
        from .plan import compile_plan
        from .runtime import run_plan
        for source in ('data d;x=1;run;title "x";proc print data=d;run;',
                       'data d;x=1;run;proc print data=d noobs;var x;run;proc print data=d noobs;var x;run;'):
            self.assertTrue(compile_plan(source).blocked)
        base=compile_plan(ORIGINAL.read_text()).to_dict()
        for old in ('data','control_data','flow_data','exchange_data'):
            bad=deepcopy(base);bad['steps'][2]['kind']=old
            with self.subTest(old=old),self.assertRaises(ValueError):run_plan(bad)
        for profile in ('binary64-v1','binary64-rows-v1','binary64-pipeline-v1'):
            bad=deepcopy(base);bad['steps'][2]['operations'][0]['args']['profile']=profile
            with self.subTest(profile=profile),self.assertRaises(ValueError):run_plan(bad)

    def test_comments_opaque_data_and_legacy_literals_do_not_select_reports(self):
        from examples.verify_mixed_print import data_source
        from .plan import compile_plan
        source=data_source(['report_title,A,1'])
        parsed=compile_plan('/* title "hidden";proc print data=x;run; */'+source)
        self.assertFalse(parsed.blocked);self.assertEqual([x.kind for x in parsed.steps],['character_data'])
        for source in ("data d;x='mixed_print logical-title-v1';run;",'data d;title=1;run;'):
            parsed=compile_plan(source);self.assertFalse(parsed.blocked)
            self.assertIsNone(validate_program(parsed.to_dict()))

    def test_exact_rendered_header_row_total_bounds(self):
        names=[('c'+str(i)).ljust(32,'x') for i in range(31)]+['tail'.ljust(28,'x')]
        schema={name:{'type':'character','length':64} for name in names};rows=[]
        self.assertEqual(len('obs '+' '.join(names)),1055)
        for observation in range(1,1001):
            difference=415-len(str(observation))-96
            slashes,remainder=divmod(difference,2);fields=['']*32
            for i in range(3):
                count=min(64,slashes);fields[i]='\\'*count;slashes-=count
            if remainder:fields[3]='a'
            self.assertEqual(slashes,0)
            rows.append({name:value.ljust(64) for name,value in zip(names,fields,strict=True)})
        catalog={'raw':{'schema':schema,'rows':rows}}
        report=execute_print(print_step(),catalog)['print_01.txt']
        self.assertEqual(len(report),417056);self.assertEqual(max(map(len,report.splitlines()[1:])),415)
        with self.assertRaises(ValueError):execute_print(print_step(),catalog,'x')
        bad=deepcopy(catalog);bad['raw']['rows'][-1][names[3]]='aa'.ljust(64)
        with self.assertRaises(ValueError):execute_print(print_step(),bad)

    def test_CPP_new_program_refuses(self):
        from examples.verify_mixed_print import ORIGINAL
        from .emit_cpp import translate
        self.assertTrue(translate(ORIGINAL.read_text()).blocked)


    def test_shared_container_DAG_is_linear_without_legacy_size_caps(self):
        import sys
        from . import mixed_reports
        dag=[]
        for _ in range(12):dag=[dag,dag]
        counter=[0]
        def lines(frame,event,arg):
            if event=='line' and frame.f_code.co_filename==mixed_reports.__file__ and frame.f_code.co_name=='refuse_legacy':
                counter[0]+=1
                if counter[0]>1000:raise AssertionError('thirteen-container DAG repeated completed nodes')
            return lines
        previous=sys.gettrace()
        try:
            sys.settrace(lines);refuse_legacy(dag)
        finally:sys.settrace(previous)
        self.assertLess(counter[0],1000)
        with self.assertRaises(ValueError):refuse_legacy([{'kind':'mixed_print'},dag])
        cycle=[];cycle.append(cycle)
        with self.assertRaises(ValueError):refuse_legacy([cycle,dag])
        refuse_legacy([{'kind':'assign','args':{'value':i}} for i in range(20001)])


    def test_TITLE_no_PRINT_preserves_fractional_NODUPKEY_identity(self):
        from examples.verify_mixed_print import batch_witness,execute,data_source,assert_tree
        simple=data_source(['X,.25','X,.5'],columns='c :$1. n')+'title "Probe";proc sort data=raw out=ordered nodupkey;by n;run;'
        extended=data_source(['X,.25','X,.5','X,.25','X,.','Y,.','X,-.5','X,-.25','X,.5'],columns='c :$1. n')+'title "Probe";proc sort data=raw out=ordered nodupkey;by n;run;'
        for source,wanted in ((simple,[.25,.5]),(extended,[None,-.5,-.25,.25,.5])):
            with self.subTest(wanted=wanted):
                witness=batch_witness([source])[0];self.assertIsNotNone(witness)
                actual=execute(source,True);assert_tree(actual['result'],witness['result'])
                self.assertEqual(actual['trace'],witness['trace'])
                self.assertEqual([row['n'] for row in actual['result']['datasets']['ordered']['rows']],wanted)
                self.assertEqual([row['c'] for row in actual['result']['datasets']['ordered']['rows']],['X']*len(wanted))
                self.assertNotIn('reports',actual['result']);self.assertEqual(actual['final_title'],'Probe')


if __name__ == '__main__':
    unittest.main()
