"""DS-030 maintainer evidence from original cases and independent base R, no live SAS."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from sas_semantics import sas_substr_checked, sas_substr
from .emit_py import translate
from .functions import validate_substr_calls
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function


def execute(source,inputs=None):
    plan=compile_plan(source)
    if plan.blocked: raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(),inputs)['datasets']['d']


class SubstrTests(unittest.TestCase):
    def test_literal_destination_inherits_source_width(self):
        table=execute("data d; x=substr('abcde',2,3); n=length(x); nn=lengthn(x); nc=lengthc(x); run;")
        self.assertEqual(table['schema']['x'],{'type':'character','length':5})
        self.assertEqual(table['rows'],[{'x':'bcd  ','n':3.,'nn':3.,'nc':5.}])
        self.assertEqual(route_function("x=substr('abc',1,1)"),('substr','DS-030'))
        self.assertIn(('substr','DS-030',1),compile_plan("data d; x=substr('abc',1,1); run;").matched)

    def test_source_descriptor_and_existing_targets(self):
        table=execute("data d; length a $8; length b $2; length c $9; a='abcde'; "
                      "copy=a; x=substr(copy,2,3); b=substr(a,2,3); c=substr(a,2,3); run;")
        self.assertEqual(table['schema']['x'],{'type':'character','length':8})
        self.assertEqual(table['rows'],[{'a':'abcde   ','b':'bc','c':'bcd      ','copy':'abcde   ','x':'bcd     '}])

    def test_first_assignment_descriptor_survives_later_sources(self):
        table=execute("data d; x=substr('abcde',2,3); x=substr('QRSTUVWXY',2,7); run;")
        self.assertEqual(table['schema']['x']['length'],5)
        self.assertEqual(table['rows'],[{'x':'RSTUV'}])
        table=execute("data d; x='Q'; x=substr('abcde',2,3); run;")
        self.assertEqual(table['rows'],[{'x':'b'}])

    def test_blank_and_edge_extractions_preserve_bytes(self):
        for source,start,size,expected in [(' aZ  ',2,3,'aZ   '),('    ',2,2,'    '),('abc',3,1,'c  ')]:
            self.assertEqual(execute(f"data d; x=substr('{source}',{start},{size}); run;")['rows'],[{'x':expected}])
        self.assertEqual(sas_substr_checked('x'*32767,32767,1),'x')
        self.assertEqual(sas_substr('abc',3,2),'c')
        with self.assertRaisesRegex(ValueError,'error-flag'): sas_substr_checked('abc',3,2)

    def test_schema_on_zero_trip_and_false_conditional(self):
        for body in ("do i=2 to 1; x=substr('abcde',2,3); end;", "if 0 then x=substr('abcde',2,3);"):
            table=execute('data d; '+body+' run;')
            self.assertEqual(table['schema']['x']['length'],5)
            self.assertEqual(table['rows'][0]['x'],' '*5)

    def test_empty_and_filtered_input_keep_schema(self):
        inputs={'raw':{'schema':{'a':{'type':'character','length':8}},'rows':[]}}
        for predicate in ('','where 0;'):
            table=execute('data d; set raw; '+predicate+' x=substr(a,2,3); run;',inputs)
            self.assertEqual(table['schema']['x']['length'],8)
            self.assertEqual(table['rows'],[])

    def test_where_uses_input_width_before_output_length_override(self):
        for input_width,target_width,start,expected in ((4,2,4,'AB'),(2,4,2,'AB  ')):
            source=f"data d; length a ${target_width}; set raw; where substr(a,{start},1)='{' ' if start==4 else 'B'}'; run;"
            for rows in ([],[{'a':'AB'}]):
                table=execute(source,{'raw':{'schema':{'a':{'type':'character','length':input_width}},'rows':rows}})
                self.assertEqual(table['schema']['a']['length'],target_width)
                self.assertEqual(table['rows'],[{'a':expected}] if rows else [])
        with self.assertRaisesRegex(ValueError,'SUBSTR'):
            execute("data d; length a $8; set raw; where substr(a,3,1)=' '; run;",
                    {'raw':{'schema':{'a':{'type':'character','length':2}},'rows':[]}})

    def test_dynamic_numeric_bounds_and_arithmetic(self):
        table=execute("data d; p=1; n=2; x=substr('abcde',p+1,n); run;")
        self.assertEqual(table['rows'][0]['x'],'bc   ')
        table=execute("data d; do i=1 to 2; x=substr('abcde',i,2); output; end; run;")
        self.assertEqual([row['x'] for row in table['rows']],['ab   ','bc   '])

    def test_invalid_static_bounds_refused_even_without_execution(self):
        for start,size in [('0','1'),('-1','1'),('1.5','1'),('.','1'),('.A','1'),('1','0'),('1','4'),('3','2'),("'1'",'1')]:
            for prefix,suffix in [('',''),('do i=2 to 1;','end;'),('if 0 then','')]:
                source=f"data d; {prefix} x=substr('abc',{start},{size}); {suffix} run;"
                with self.subTest(source=source),self.assertRaisesRegex(ValueError,'SUBSTR'):
                    execute(source)
            source=f"data d; set raw; where 0; x=substr(a,{start},{size}); run;"
            with self.assertRaisesRegex(ValueError,'SUBSTR'):
                execute(source,{'raw':{'schema':{'a':{'type':'character','length':3}},'rows':[]}})

    def test_source_types_and_bound_types_checked_on_empty_input(self):
        for schema in ({'a':'number','p':'number'}, {'a':{'type':'character','length':3},'p':{'type':'character','length':1}}):
            with self.assertRaisesRegex(ValueError,'SUBSTR'):
                execute('data d; set raw; x=substr(a,p,1); run;',{'raw':{'schema':schema,'rows':[]}})
        for source in ("x=substr(123,1,1)","x=substr('',1,1)","x=substr(put(1,4.0),1,1)"):
            with self.assertRaisesRegex(ValueError,'SUBSTR'): execute('data d; '+source+'; run;')

    def test_late_dynamic_failure_is_atomic_in_runtime_emitter_and_job(self):
        source="data d; set raw; x=substr(a,p,n); put 'seen'; output; run;"
        for invalid in (0,-1,1.5,None,4):
            inputs={'raw':{'schema':{'a':{'type':'character','length':3},'p':'number','n':'number'},
                           'rows':[{'a':'abc','p':1,'n':1},{'a':'abc','p':invalid,'n':1}]}}
            printed=io.StringIO()
            with contextlib.redirect_stdout(printed),self.assertRaisesRegex(ValueError,'SUBSTR'):
                run_plan(compile_plan(source).to_dict(),inputs)
            self.assertEqual(printed.getvalue(),'')
            namespace={'inputs':inputs};translated=translate(source)
            with contextlib.redirect_stdout(printed),self.assertRaisesRegex(ValueError,'SUBSTR'):
                exec(translated.code,namespace)
            self.assertNotIn('result',namespace)
            self.assertEqual(printed.getvalue(),'')
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'inputs.json';path.write_text(json.dumps(inputs))
                with contextlib.redirect_stdout(printed): job=build_job(source,inputs=path)
            self.assertEqual(job.code,1);self.assertIsNone(job.result)
            self.assertEqual(printed.getvalue(),'');self.assertFalse(job.receipt['accepted'])

    def test_padding_insensitive_legacy_consumers(self):
        table=execute("data d; n=length(substr(' aZ  ',2,3)); nn=lengthn(substr('    ',2,2)); "
                      "c=count(substr('aZaZ ',1,4),'Z'); if substr('abcde',2,3)='bcd' then flag=1; run;")
        self.assertEqual(table['rows'],[{'n':2.,'nn':0.,'c':2.,'flag':1.}])

    def test_unproven_temporary_consumers_refused_by_compiler_and_runtime(self):
        for expr in ("lengthc(substr('abcde',2,3))", "count(substr('abcde',2,3),' ')",
                     "count('abcde',substr('abcde',2,3))", "substr(substr('abcde',2,3),1,1)",
                     "input(substr('12345',1,2))", "substr('12345',1,2)+1"):
            source='data d; x='+expr+'; run;'
            job=build_job(source);self.assertEqual(job.code,2);self.assertIsNone(job.result)
            with self.assertRaisesRegex(ValueError,'SUBSTR'):
                run_plan(job.plan.to_dict(),allow_partial=True)

    def test_global_quarantine_remains(self):
        for tail in ("r=reverse(x);", "length a b $3;", "r='a'!!'b';", "r=catx('|','a','b');"):
            source="data first; x=substr('abcde',2,3); run; data d; "+tail+' run;'
            job=build_job(source);self.assertEqual(job.code,2)
            with self.assertRaisesRegex(ValueError,'quarantin'):run_plan(job.plan.to_dict(),allow_partial=True)
        self.assertFalse(compile_plan("data d; x='substr(a,1,2)'; r=reverse(x); run;").blocked)

    def test_source_wide_guards_and_cpp_refusal(self):
        for literal in ('"&macro"',"'é'","'a\tb'"):
            self.assertEqual(build_job("data d; x=substr('abcde',2,3); unused="+literal+'; run;').code,2)
        self.assertEqual(build_job("data d; x=substr('abcde',2,3); run;",target='cpp').code,2)
        self.assertEqual(build_job("data d; x=substr('abcde',2); run;").code,2)

    def test_malformed_call_has_visible_refusal(self):
        for args in ([],[{'kind':'character','value':'abc'}],None):
            with self.assertRaisesRegex(ValueError,'SUBSTR'):
                validate_substr_calls({'kind':'call','name':'substr','args':args},{})


if __name__=='__main__': unittest.main()
