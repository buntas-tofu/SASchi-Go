"""DS-042 source, output scheduling, atomic refusals and whole-file evidence."""
import contextlib
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from examples.verify_put_mixed_numeric import PINS, REFUSALS, original_expected, original_witness, program_witness
from sas_semantics import sas_put_mixed_numeric
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from .test_parser import ROKU_CORPUS

ORIGINAL=Path(__file__).resolve().parents[1]/'examples/mixed_put_capture.sas'
SOURCE_SHA='e708b988d5d9f852cef56150068abeb9eda8bb3ca3eb59d04457429e930d2aa1'
RESULT_SHA='de6deb664a12c7c59152d6b2a57baf70d80a6d14652135ef4bfe3e98bd600273'
STDOUT_SHA='7fdf31c4f5a69dffc4113dc222c537f347029cfe0ea6f55b01f2c21b3fb9649e'

def catalog(values,spec='number'):
    return {'raw':{'schema':{'n':spec},'rows':[{'n':v} for v in values]}}


class MixedNumericPutTests(unittest.TestCase):
    def test_reference_pins_and_refusals(self):
        for items,expected in PINS:self.assertEqual(sas_put_mixed_numeric(items),expected)
        for items in REFUSALS:
            with self.subTest(items=items),self.assertRaises(ValueError):sas_put_mixed_numeric(items)
        with self.assertRaises(ValueError):sas_put_mixed_numeric([{'kind':'literal','value':"'x'"},{'kind':'numeric','value':10**5000}])

    def test_shape_marker_provenance_and_version(self):
        p=compile_plan("data d; n=7;\nput '[' n ']';run;")
        self.assertFalse(p.blocked,p.tickets);self.assertEqual(p.version,2)
        self.assertEqual(p.steps[0].operations[-1].args,{'items':[{'kind':'literal','value':"'['"},{'kind':'variable','value':'n'},{'kind':'literal','value':"']'"}]})
        self.assertIn(('put-mixed-numeric','DS-042',2),p.matched)
        p.version=1
        with self.assertRaises(ValueError):run_plan(p.to_dict())

    def test_literal_blank_and_terminal_separator_pins(self):
        source="data d; n=7; put 'prefix  ' n; put n ' suffix'; put '[' n ']'; put 'a' 'b' n;run;"
        result,stdout=execute(source)
        self.assertEqual(result['log'],['prefix  7 ','7  suffix','[7 ]','ab7 '])
        self.assertEqual(stdout,'prefix  7 \n7  suffix\n[7 ]\nab7 \n')
        self.assertEqual(result['datasets']['d']['rows'],[{'n':7.}])

    def test_quoted_tokens_escape_and_empty_quote(self):
        source='''data _null_; n=0; put 'O''Neil:' n "a""b" '' "";run;'''
        self.assertEqual(execute(source)[1],'''O'Neil:0 a"b'"\n''')

    def test_adjacent_typed_literal_and_comment_only_gap_refuse(self):
        for tail in ("'41'n", "'41'/*c*/ n", "'41'n 'tail'", "'41'x", "'01JAN2020'd"):
            self.assertEqual(build_job('data d;n=1;x=1;d=1;put '+tail+';run;').code,2)
        for gap in (' ','\t','\n',' /*c*/ '):
            self.assertEqual(execute("data d;n=1;put '41'"+gap+'n;run;')[1],'411 \n')

    def test_source_order_type_evidence_is_required(self):
        for source in ("data d;put 'x' n;n=7;run;", "data d;n=7;put 'x' n unknown;run;",
                       "data d;set raw;put 'x' n;run;", "data d;set raw;copy=n;put 'x' copy;run;"):
            self.assertIn(job_with_inputs(source,catalog([7])).code,(1,2))
        source="data d;set raw;if 0 then n=.;put 'x' n;run;"
        self.assertEqual(execute(source,catalog([7,None,-3]))[0]['log'],['x7 ','x. ','x-3 '])

    def test_unknown_does_not_become_known_from_future_statement(self):
        p=compile_plan("data d;put '[' n ']';if 0 then n=0;run;")
        self.assertTrue(p.blocked)

    def test_old_put_plan_shapes_and_output_remain(self):
        source="data d;c=' A ';n=7;put 'a' 'b';put '[' c ']';put n;put n=;run;"
        p=compile_plan(source);self.assertFalse(p.blocked)
        self.assertEqual([o.kind for o in p.steps[0].operations],['assign','assign','put_literal','put_character_list','put_numeric_list','put'])
        self.assertEqual(execute(source)[0]['log'],['ab','[A ]','7 ','n=7'])

    def test_character_numeric_variable_mixtures_stay_closed(self):
        for source in ("data d;n=1;c='a';put 'x' n c;run;", "data d;n=1;c='a';put n c;run;"):
            self.assertIn(build_job(source).code,(1,2))
        self.assertEqual(execute("data d;c='a';put 'x' c;run;")[1],'xa \n')

    def test_boundaries_missing_and_negative_zero(self):
        source="data d; a=-99999999999;b=99999999999;c=-0.;d=.;put '[' a b c d ']';run;"
        self.assertEqual(execute(source)[1],'[-99999999999 99999999999 0 . ]\n')

    def test_static_minimum_and_dynamic_width_boundaries(self):
        source="data d;n=0;put '"+'x'*62+"' n;run;"
        self.assertEqual(execute(source)[1],'x'*62+'0 \n')
        self.assertEqual(build_job(source.replace('n=0','n=-1')).code,1)
        self.assertEqual(build_job(source.replace('x'*62,'x'*63)).code,2)
        # A final literal consumes one column; each numeric item consumes at least two.
        self.assertEqual(build_job('data d;n=0;put '+ 'n '*32+"'x';run;").code,2)

    def test_dynamic_failure_after_prior_output_is_atomic(self):
        for value in ('1.25','100000000000','-100000000000','.A','._'):
            source="data d;n=7;put 'ok' n;output;n="+value+";\nput 'bad' n;run;"
            job=build_job(source);self.assertEqual(job.code,1);self.assertIsNone(job.result)
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaisesRegex(ValueError,'SAS line 2'):
                exec(translate(source).code,{})
            self.assertEqual(stream.getvalue(),'')

    def test_late_input_row_failure_is_atomic(self):
        source="data d;set raw;if 0 then n=.;put 'n:' n;output;run;"
        for value in (1.5,{'missing':'A'}):
            job=job_with_inputs(source,catalog([7,value]));self.assertEqual(job.code,1);self.assertIsNone(job.result)
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':catalog([7,value])})
            self.assertEqual(stream.getvalue(),'')

    def test_schema_formats_even_empty_filtered_and_skipped(self):
        for rows,where in (([],''),([7],'where 0;')):
            for spec in ({'type':'number','format':'BEST12.'},{'type':'character','length':1}):
                raw=catalog(rows if spec['type']=='number' else ['a'] if rows else [],spec)
                source="data d;set raw;"+where+"if 0 then n=.;if 0 then put 'n:' n;run;"
                job=job_with_inputs(source,raw);self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_input_metadata_is_preserved(self):
        spec={'type':'number','length':8,'label':'count'}
        result,stdout=execute("data d;set raw;if 0 then n=.;put 'n:' n;run;",catalog([7],spec))
        self.assertEqual(result['datasets']['d'],{'schema':{'n':spec},'rows':[{'n':7.}]})
        self.assertEqual(stdout,'n:7 \n')

    def test_late_set_order_still_refuses(self):
        job=job_with_inputs("data d;n=1;put 'n:' n;set raw;run;",catalog([],{'type':'number','format':'BEST12.'}))
        self.assertEqual(job.code,2)
        self.assertIsNone(job.result)

    def test_unreached_dynamic_value_is_lazy(self):
        result,stdout=execute("data d;n=1.5;if 0 then put 'n:' n;do i=2 to 1;put 'n:' n;end;run;")
        self.assertEqual(stdout,'');self.assertEqual(result['log'],[])

    def test_selected_if_else_and_nested_counted_scheduling(self):
        source="data d;do i=1 to 2;do j=1 to i;if j=1 then put '[' i j ']';else put 'else:' j;end;end;run;"
        result,stdout=execute(source)
        self.assertEqual(result['log'],['[1 1 ]','[2 1 ]','else:2 '])
        self.assertEqual(stdout,'[1 1 ]\n[2 1 ]\nelse:2 \n')
        self.assertEqual(result['datasets']['d']['rows'],[{'i':3.,'j':3.}])

    def test_put_does_not_output_rows_or_change_output_suppression(self):
        result,stdout=execute("data d;n=1;put '[' n ']';if 0 then output;run;")
        self.assertEqual(result['datasets']['d']['rows'],[]);self.assertEqual(stdout,'[1 ]\n')

    def test_row_run_and_catalog_state_isolation(self):
        source="data d;set raw;if 0 then n=.;put 'prior:' scratch; scratch=n;run;"
        # Unknown variables still refuse. Establish scratch's type on a skipped path.
        source=source.replace("put 'prior:'", "if 0 then scratch=.;put 'prior:'")
        p=compile_plan(source).to_dict();raw=catalog([1,2]);before=deepcopy((p,raw))
        a=run_plan(p,raw);self.assertEqual(a['log'],['prior:. ','prior:. '])
        self.assertEqual(run_plan(p,raw),a);self.assertEqual((p,raw),before)

    def test_global_macro_ascii_guards_and_safe_single_quotes(self):
        for suffix in ('unused="&name";', 'unused="%call(x)";', "unused='é';"):
            self.assertEqual(build_job("data d;n=1;put 'n:' n;"+suffix+'run;').code,2)
        self.assertEqual(execute("data d;n=1;put '&name %call:' n;run;")[1],'&name %call:1 \n')

    def test_output_syntax_boundaries(self):
        for statement in ("put '[' n best12.","put '[' n : best12.","put '[' n @", "put '[' n @@",
                          "put @4 '[' n", "put '[' n /", "put '[' n +1", "put '[' (n)","put '[' 7",
                          "put '[' n+1", "put '[' abs(n)","put 2*'[' n", "file log;put '[' n"):
            self.assertEqual(build_job('data d;n=1;'+statement+';run;').code,2,statement)

    def test_reserved_names_and_array_controls_refuse(self):
        for name in ('_n_','_error_','_all_','_numeric_','_character_','_temporary_','_infile_','_file_','_ods_','_page_','_blankpage_'):
            self.assertEqual(build_job('data d;'+name+"=1;put '[' "+name+';run;').code,2,name)
        for tail in ('a','a[1]','sum(of a[*])'):
            self.assertIn(build_job("data d;array a x;x=1;put '[' "+tail+';run;').code,(1,2))
        self.assertEqual(execute("data d;array a x;x=1;put '[' x;run;")[1],'[1 \n')

    def test_other_loop_and_backend_boundaries(self):
        for body in ("do while(n<2);put '[' n;n=n+1;end;", "do until(n>1);put '[' n;n=n+1;end;",
                     "array a x;do over a;put '[' n;end;"):
            self.assertEqual(build_job('data d;n=1;'+body+'run;').code,2,body)
        self.assertEqual(build_job(ORIGINAL.read_text(),target='cpp').code,2)
        bitwise=build_job((ROKU_CORPUS/'bitwise_operations.sas').read_text())
        self.assertEqual(bitwise.code,1)
        self.assertIsNone(bitwise.result)

    def test_independent_malformed_plan_validation(self):
        original=compile_plan("data d;n=1;put '[' n;run;").to_dict()
        bad=[None,[],{},[{}],[{'kind':[],'value':0}],
             [{'kind':'literal','value':"'x'"},{'kind':'variable','value':[]}],
             [{'kind':'literal','value':"'x'"},{'kind':'variable','value':'N'}],
             [{'kind':'literal','value':"'x'"},{'kind':'variable','value':'_n_'}],
             [{'kind':'literal','value':"'x'"},{'kind':'variable','value':'unknown'}],
             [{'kind':'numeric','value':1},{'kind':'literal','value':"'x'"}],
             [{'kind':'literal','value':"'x'",'extra':0},{'kind':'variable','value':'n'}],
             [{'kind':'literal','value':"'x'"}]*65]
        for items in bad:
            p=deepcopy(original);p['steps'][0]['operations'][-1]['args']['items']=items
            with self.subTest(items=items),self.assertRaises(ValueError):run_plan(p)
        for change in ('extra','missing','version','line','kind','character'):
            p=deepcopy(original);op=p['steps'][0]['operations'][-1]
            if change=='extra':op['args']['extra']=1
            elif change=='missing':op['args']={}
            elif change=='version':p['version']=1
            elif change=='line':op['line']=True
            elif change=='kind':p['steps'][0]['kind']='merge'
            else:p['steps'][0]['operations'][0]['args']['value']={'kind':'character','value':'x'}
            with self.subTest(change=change),self.assertRaises(ValueError):run_plan(p)

    def test_forged_non_counted_container_refuses(self):
        p=compile_plan("data d;n=1;do while(n<2);n=n+1;end;put '[' n;run;").to_dict()
        op=p['steps'][0]['operations'].pop();p['steps'][0]['operations'][1]['args']['body'].append(op)
        with self.assertRaises(ValueError):run_plan(p)

    def test_original_complete_program_source_result_stdout_R(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'a24331f7dc7ca0a41c06e72919d2aa072fb742db45d6f0b630089f92b2eeaa45')
        result,stdout=execute(ORIGINAL.read_text())
        self.assertEqual(result,original_expected());self.assertEqual(result,original_witness())
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'e54cb5fa6ec9cffc5147ec3fde8da0ea1c9a1f97163e3ffb5e3ffcc8a3dc94f6')
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),'9f973f0f7ac3a3b793518140675aa22132b13a4e35e447e98d82dc402c1a93b1')

    def test_dataset_comparator_value_order_schema_multiplicity(self):
        for mutation in ('value','order','schema','multiplicity'):
            expected=original_expected()['datasets'];t=expected['records']
            if mutation=='value':t['rows'][0]['x']=9.
            elif mutation=='order':t['rows'].reverse()
            elif mutation=='schema':t['schema']=dict(reversed(list(t['schema'].items())))
            else:t['rows'].append(deepcopy(t['rows'][0]))
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'expected.json';p.write_text(json.dumps(expected))
                job=build_job(ORIGINAL.read_text(),expect=p)
                self.assertEqual(job.code,1);self.assertFalse(job.receipt['accepted']);self.assertEqual(job.result,original_expected())

    def test_full_unmodified_external_program(self):
        path=ROKU_CORPUS/'100_doors.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),SOURCE_SHA)
        expected={'datasets':{},'log':['Number of Open Doors:  10 ']}
        result,stdout=execute(path.read_text());self.assertEqual(result,expected)
        self.assertEqual(stdout,'Number of Open Doors:  10 \n')
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),STDOUT_SHA)
        self.assertEqual(hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest(),RESULT_SHA)
        self.assertEqual(program_witness(path),expected['log'][0])
        job=build_job(path.read_text());self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted'])
        self.assertEqual(job.result,expected);self.assertEqual(job.receipt['source_sha256'],SOURCE_SHA)
        # Exact log controls complement the dataset-only public comparator contract.
        for wrong in ('Number of Open Doors: 10 ','Number of Open Doors:  10','Number of Open Doors:  9 '):
            self.assertNotEqual(result['log'],[wrong])
        self.assertNotEqual(result['log'],expected['log']*2)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'cli'
            r=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(json.loads((out/'result.json').read_text()),expected)
            self.assertTrue(json.loads((out/'receipt.json').read_text())['accepted'])
        print('VERIFIED corpus: 100_doors.sas; full source/stdout/result pins, CLI, divisor-parity hand proof and independent base R; no live SAS')

    def test_R_whole_program_parser_accounts_for_tail_and_bindings(self):
        from examples.verify_put_mixed_numeric import rrun
        source=(ROKU_CORPUS/'100_doors.sas').read_text()
        for bad in (source+'put "extra";',source.replace('by Pass','by Current')):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'mutated.sas';p.write_text(bad)
                with self.assertRaises(subprocess.CalledProcessError):rrun('program',p)


if __name__=='__main__':unittest.main()
