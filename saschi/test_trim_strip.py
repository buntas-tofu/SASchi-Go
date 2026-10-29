"""DS-043 fixed descriptors, shortened values, refusals and complete programs."""
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

from examples.verify_trim_strip import ORIGINAL, PINS, REFUSALS, original_expected, program_witness, rrun
from sas_semantics import sas_trim, sas_strip, sas_trim_concat, sas_concat
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .test_do_counted import execute, job_with_inputs
from .test_parser import ROKU_CORPUS
from .trim_strip import validate_expression

SOURCE_SHA='88ad65e242857efa846bf34618e7b99ec4fba3dec8b3357033a9458759f39f87'
RESULT_SHA='94e92f8365b10f40383ed27e1e28e0ea9788bebbf34b1c7d87b5a5c03eb6549a'
STDOUT_SHA='fa3e879dbbcc99fb4765c74272d862e330c8de985cbaac87b75db36ceab10699'


def catalog(values, spec=None):
    return {'raw':{'schema':{'a':spec or {'type':'character','length':4}},'rows':[{'a':v} for v in values]}}


def digest(result):
    return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class TrimStripTests(unittest.TestCase):
    def test_reference_pins_and_refusals(self):
        for mode,value,expected in PINS:
            self.assertEqual((sas_trim if mode=='trim' else sas_strip)(value),expected)
        for f in (sas_trim,sas_strip):
            for value in REFUSALS:
                with self.subTest(function=f.__name__,value=repr(value)[:50]),self.assertRaises(ValueError):f(value)

    def test_reference_width_limits_and_blank_distinction(self):
        self.assertEqual(sas_trim(' '*32767),' ')
        self.assertEqual(sas_strip(' '*32767),'')
        self.assertEqual(sas_strip('X'*32767),'X'*32767)
        self.assertEqual(sas_trim_concat(['',''],[True,True]),'')
        self.assertEqual(sas_trim_concat(['X'*32766,'!'],[True,False]),'X'*32766+'!')
        with self.assertRaises(ValueError):sas_trim_concat(['X'*32767,'!'],[True,False])

    def test_legacy_concat_remains_strict(self):
        self.assertEqual(sas_concat(['A  ','!']),'A  !')
        for args,flags in [(['','!'],[False,True]),(['A','!'],[False,False]),(['A'],[True]),(['A','!'],[1,False])]:
            with self.assertRaises(ValueError):sas_trim_concat(args,flags)
        with self.assertRaises(ValueError):sas_concat(['','!'])

    def test_plan_provenance_and_version(self):
        p=compile_plan("data d; a=' X ';\nb=trim(a);c=strip(a);run;")
        self.assertFalse(p.blocked,p.tickets);self.assertEqual(p.version,2)
        self.assertIn(('trim-strip','DS-043',2),p.matched)
        p.version=1
        with self.assertRaises(ValueError):run_plan(p.to_dict())

    def test_assignment_inherits_argument_width_and_repads(self):
        result,_=execute("data d;length a $5;a=' X ';t=trim(a);s=strip(a);run;")
        self.assertEqual(result['datasets']['d'],{'schema':{n:{'type':'character','length':5} for n in ('a','t','s')},
            'rows':[{'a':' X   ','t':' X   ','s':'X    '}]})

    def test_literal_arguments_and_declared_destination(self):
        result,_=execute("data d;length a $2;length b $7;a=trim(' AB ');b=strip(' AB ');c=strip(' ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' A','b':'AB     ','c':' '}])
        self.assertEqual(result['datasets']['d']['schema']['c'],{'type':'character','length':1})

    def test_concat_uses_shortened_values_and_fixed_other_operands(self):
        result,_=execute("data d;length a $4;a=' X ';t='['||trim(a)||']';s='['!!strip(a)!!']';fixed=a||strip(a);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' X  ','t':'[ X]  ','s':'[X]   ','fixed':' X  X   '}])
        self.assertEqual(result['datasets']['d']['schema']['fixed'],{'type':'character','length':8})

    def test_two_empty_temporary_operands_assign_blank_storage(self):
        result,_=execute("data d;a=strip(' ')||strip('  ');b=trim(' ')||strip(' ');run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'   ','b':'  '}])

    def test_static_concat_operand_and_width_limits(self):
        self.assertEqual(build_job("data d;a="+'||'.join(["strip(' ')"]*32)+';run;').code,0)
        self.assertIn(build_job("data d;a="+'||'.join(["strip(' ')"]*33)+';run;').code,(1,2))
        self.assertEqual(build_job("data d;length a $32766;b=strip(a)||'!';run;").code,0)
        self.assertEqual(build_job("data d;length a $32767;b=strip(a)||'!';run;").code,1)

    def test_schema_discovery_on_skipped_and_zero_trip_paths(self):
        result,_=execute("data d;length a $4;if 0 then x=strip(a);do i=2 to 1;y=trim(a)||'!';end;run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'    ','x':'    ','i':2.,'y':'     '}])
        self.assertEqual(list(result['datasets']['d']['schema']),['a','x','i','y'])

    def test_empty_and_filtered_input_keep_new_schema(self):
        for values,where in (([],''),([' X '],'where 0;')):
            result,_=execute('data d;set raw;'+where+'if 0 then b=strip(a);run;',catalog(values))
            self.assertEqual(result['datasets']['d'],{'schema':{'a':{'type':'character','length':4},'b':{'type':'character','length':4}},'rows':[]})

    def test_unknown_numeric_and_future_descriptors_refuse_eagerly(self):
        for source in ("data d;if 0 then b=strip(a);a='x';run;", "data d;length a 8;if 0 then b=strip(a);run;",
                       "data d;if 0 then b=trim(1);run;", "data d;b=strip(_n_);run;"):
            self.assertIn(build_job(source).code,(1,2),source)
        for values in ([],[1]):
            self.assertEqual(job_with_inputs('data d;set raw;where 0;if 0 then b=strip(a);run;',catalog(values,'number')).code,1)

    def test_input_metadata_preserved_and_result_width_only(self):
        spec={'type':'character','length':4,'label':'original','format':'$CHAR4.'}
        result,_=execute('data d;set raw;b=strip(a);run;',catalog([' X '],spec))
        self.assertEqual(result['datasets']['d']['schema'],{'a':spec,'b':{'type':'character','length':4}})
        self.assertEqual(result['datasets']['d']['rows'],[{'a':' X  ','b':'X   '}])

    def test_row_run_step_reset_and_catalog_immutability(self):
        source="data d;length scratch $4;set raw;before=strip(scratch)||'!';scratch=strip(a);run;data e;length scratch $4;x=strip(scratch)||'?';run;"
        p=compile_plan(source).to_dict();raw=catalog([' A ',' B ']);before=deepcopy((p,raw))
        result=run_plan(p,raw)
        self.assertEqual([r['before'] for r in result['datasets']['d']['rows']],['!    ']*2)
        self.assertEqual([r['scratch'] for r in result['datasets']['d']['rows']],['A   ','B   '])
        self.assertEqual(result['datasets']['e']['rows'],[{'scratch':'    ','x':'?    '}])
        self.assertEqual(run_plan(p,raw),result);self.assertEqual((p,raw),before)

    def test_in_place_assignment_reads_actual_row_variable(self):
        result,_=execute("data d;length a $4;a=' A ';a=strip(a)||'B';copy=a;a=trim(a)||'C';run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'ABC ','copy':'AB  '}])

    def test_if_else_and_nested_counted_output_snapshots(self):
        result,_=execute("data d;length a $4;do i=1 to 2;do j=1 to i;if j=1 then a=strip(a)||'*';else a=trim(a)||'!';output;end;end;run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'*   ','i':1.,'j':1.},{'a':'**  ','i':2.,'j':1.},{'a':'**! ','i':2.,'j':2.}])
        self.assertEqual(list(result['datasets']['d']['schema']),['a','i','j'])

    def test_skipped_output_suppresses_implicit_row(self):
        result,stdout=execute("data d;a=strip(' X ');put a;if 0 then output;run;")
        self.assertEqual(result['datasets']['d']['rows'],[]);self.assertEqual(stdout,'X \n')

    def test_late_dynamic_failure_is_atomic(self):
        source='data d;set raw;b=strip(a);put b;output;run;'
        for value in ('é','a\tb'):
            raw=catalog(['OK',value]);job=job_with_inputs(source,raw)
            self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':raw})
            self.assertEqual(stream.getvalue(),'')

    def test_unreached_dynamic_character_value_is_lazy(self):
        result,_=execute('data d;set raw;if 0 then b=strip(a);run;',catalog(['é']))
        self.assertEqual(result['datasets']['d']['rows'][0]['b'],'    ')

    def test_temporary_consumers_and_nested_arguments_refuse(self):
        for rhs in ("strip(trim(a))","length(strip(a))","reverse(trim(a))","substr(strip(a),1,1)","catx('-',strip(a),'x')","strip(a||'x')","strip(a)+1","strip(a)||reverse(a)"):
            self.assertIn(build_job("data d;a=' X ';b="+rhs+';run;').code,(1,2),rhs)
        for use in ("if strip(a)='X' then b=1;","where strip(a)='X';","put strip(a);"):
            self.assertIn(build_job("data d;a='X';"+use+'run;').code,(1,2))

    def test_global_ascii_macro_guards_and_literal_token_safety(self):
        for suffix in ('unused="&name";','unused="%call(x)";',"unused='é';"):
            self.assertEqual(build_job("data d;a=strip('x');"+suffix+'run;').code,2)
        self.assertEqual(build_job("data d;a=strip('&name %call');run;").code,0)
        self.assertEqual(build_job("data d;a='strip(x)';run;").code,0)

    def test_other_containers_and_backend_remain_refused(self):
        for body in ("do while(n<2);a=strip(a);n=n+1;end;","do until(n>1);a=trim(a);n=n+1;end;","array z x;do over z;a=strip(a);end;"):
            self.assertEqual(build_job("data d;length a $4;n=1;"+body+'run;').code,2)
        self.assertEqual(build_job("data d;a=strip('x');put _all_;run;").code,2)
        self.assertEqual(build_job(ORIGINAL.read_text(),target='cpp').code,2)

    def test_malformed_call_shapes_refuse_independently(self):
        original=compile_plan("data d;a=' X ';b=strip(a);run;").to_dict()
        bad=[None,[],{},[{}],[{'kind':'variable','value':[]}],[{'kind':'variable','value':'A'}],
             [{'kind':'variable','value':'_n_'}],[{'kind':'variable','value':'missing'}],
             [{'kind':'number','value':1}],[{'kind':'character','value':''}],
             [{'kind':'character','value':'é'}],[{'kind':'character','value':'x','extra':0}],
             [{'kind':'variable','value':'a'}]*2,({'kind':'variable','value':'a'},)]
        for args in bad:
            p=deepcopy(original);p['steps'][0]['operations'][-1]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(p)
        for mutation in ('extra','missing','version','merge'):
            p=deepcopy(original);call=p['steps'][0]['operations'][-1]['args']['value']
            if mutation=='extra':call['extra']=0
            elif mutation=='missing':del call['args']
            elif mutation=='version':p['version']=1
            else:p['steps'][0]['kind']='merge'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):run_plan(p)

    def test_forged_concat_and_temporary_consumer_refuse(self):
        p=compile_plan("data d;a='x';b=strip(a);run;").to_dict();call=p['steps'][0]['operations'][-1]['args']['value']
        for expr in ({'kind':'concat','args':[call]}, {'kind':'concat','args':[call,call],'extra':0},
                     {'kind':'call','name':'length','args':[call]},
                     {'kind':'concat','args':[call,{'kind':'call','name':'reverse','args':[{'kind':'variable','value':'a'}]}]}):
            q=deepcopy(p);q['steps'][0]['operations'][-1]['args']['value']=expr
            with self.assertRaises(ValueError):run_plan(q)
        p['steps'][0]['operations'][-1]['kind']='sum_statement'
        with self.assertRaises(ValueError):run_plan(p)

    def test_forged_descriptor_widths_and_deep_source_refuse(self):
        for width in (0,32768,True,1.5):
            with self.assertRaises(ValueError):validate_expression({'kind':'call','name':'strip','args':[{'kind':'variable','value':'a'}]},
                {'a':{'type':'character','length':width}},context='assignment')
        self.assertEqual(build_job("data d;a="+'strip('*1500+"'x'"+')'*1500+';run;').code,2)

    def test_partial_translation_cannot_bypass_refusal(self):
        source="data d;a='x';b=strip(trim(a));run;"
        translated=translate(source,allow_partial=True)
        self.assertTrue(translated.blocked)
        self.assertEqual(build_job(source).code,2)

    def test_original_complete_program_pins_R_and_CLI(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'b68612c0a80b501e0785547336210dd94c461c6f8df0c9c0a4e0107c986e7b32')
        result,stdout=execute(ORIGINAL.read_text());independent,accounting=program_witness(ORIGINAL)
        self.assertEqual(result,original_expected());self.assertEqual(result,independent)
        self.assertEqual(digest(result),'6d279b226da98becf45fc40fb528fa670ca7c937b8ca57a08c994a57fa8561e9')
        self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),'d01d92ad8ef03cb7196048523a2b7df966d6475bcf1ee69476f3b64495a0bdea')
        self.assertEqual(accounting['statements'],26);self.assertEqual(accounting['trips'],[0,3])
        self.check_cli(ORIGINAL,result)

    def test_comparator_controls_value_order_schema_multiplicity(self):
        for mutation in ('value','order','schema','multiplicity'):
            expected=original_expected()['datasets'];table=expected['capture']
            if mutation=='value':table['rows'][0]['s']='bad '
            elif mutation=='order':table['rows'].reverse()
            elif mutation=='schema':table['schema']=dict(reversed(list(table['schema'].items())))
            else:table['rows'].append(deepcopy(table['rows'][0]))
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'expected.json';p.write_text(json.dumps(expected));job=build_job(ORIGINAL.read_text(),expect=p)
                self.assertEqual(job.code,1);self.assertFalse(job.receipt['accepted']);self.assertEqual(job.result,original_expected())

    def check_cli(self,path,expected):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'cli'
            r=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(out)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual(json.loads((out/'result.json').read_text()),expected)
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertTrue(receipt['accepted']);self.assertEqual(receipt['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_full_unmodified_external_program_both_steps(self):
        path=ROKU_CORPUS/'loops_for.sas'
        if not path.is_file():self.skipTest('Roku corpus not present')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),SOURCE_SHA)
        expected={'datasets':{},'log':[('*'*i+' ') for i in range(1,6)]*2}
        result,stdout=execute(path.read_text());independent,accounting=program_witness(path)
        self.assertEqual(result,expected);self.assertEqual(independent,expected)
        self.assertEqual(digest(result),RESULT_SHA);self.assertEqual(hashlib.sha256(stdout.encode()).hexdigest(),STDOUT_SHA)
        self.assertEqual(accounting,{'statements':17,'steps':['_null_','_null_'],
            'states':[{'a':'*****','n':6.,'i':6.},{'a':'*****','n':6.}],'trips':[15,5]})
        job=build_job(path.read_text());self.assertEqual(job.code,0);self.assertTrue(job.receipt['accepted']);self.assertEqual(job.result,expected)
        self.check_cli(path,expected)
        for wrong in (expected['log'][:5],expected['log'][::-1],[x.rstrip() for x in expected['log']],expected['log']*2):
            self.assertNotEqual(result['log'],wrong)
        print('VERIFIED corpus: loops_for.sas; both complete DATA steps, source/result/stdout pins, CLI, hand accounting and independent base R; no live SAS')

    def test_independent_R_parser_refuses_unhandled_tail_and_bindings(self):
        source=ORIGINAL.read_text()
        for bad in (source+'put "extra";',source.replace('to 3','to unknown'),source.replace('run;data','data')):
            # The missing RUN control is explicit, independent of whitespace layout.
            if bad==source:bad=source.replace('run;','',1)
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'bad.sas';p.write_text(bad)
                with self.assertRaises(subprocess.CalledProcessError):rrun('program',p)


if __name__=='__main__':unittest.main()
