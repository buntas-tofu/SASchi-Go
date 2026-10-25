"""Bounded composition acceptance/refusal receipts for maintainers, no live SAS."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan


def execute(source,inputs=None):
    plan=compile_plan(source)
    if plan.blocked: raise AssertionError(plan.tickets)
    return run_plan(plan.to_dict(),inputs)


class SubstrCompositionTests(unittest.TestCase):
    def test_grouped_length_stored_reverse_and_concat(self):
        source="data d; length a b $5; a='ABCDE'; b=substr(a,2,3); r=reverse(b); c=b!!'Q'; n=lengthc(b); run;"
        self.assertEqual(execute(source)['datasets']['d'],{
            'schema':{'a':{'type':'character','length':5},'b':{'type':'character','length':5},
                      'r':{'type':'character','length':5},'c':{'type':'character','length':6},'n':'number'},
            'rows':[{'a':'ABCDE','b':'BCD  ','r':'  DCB','c':'BCD  Q','n':5.}]})

    def test_new_substr_default_is_preserved_through_copy(self):
        row=execute("data d; a='ABCDE'; x=substr(a,2,3); y=x; r=reverse(y); c=y||'Q'; run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':'ABCDE','x':'BCD  ','y':'BCD  ','r':'  DCB','c':'BCD  Q'})

    def test_predeclared_substr_width_controls_its_consumers(self):
        for width,stored,rev in [(2,'BC','CB'),(7,'BCD    ','    DCB')]:
            row=execute(f"data d; length x ${width}; x=substr('ABCDE',2,3); r=reverse(x); c=x!!'Q'; run;")['datasets']['d']['rows'][0]
            self.assertEqual(row,{'x':stored,'r':rev,'c':stored+'Q'})

    def test_set_carries_substr_descriptor_across_steps(self):
        result=execute("data prior; x=substr('ABCDE',2,3); run; data d; set prior; r=reverse(x); c=x!!'Q'; run;")
        self.assertEqual(result['datasets']['d']['schema']['x'],{'type':'character','length':5})
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'BCD  ','r':'  DCB','c':'BCD  Q'}])

    def test_unrelated_operations_across_steps_do_not_block(self):
        result=execute("data prior; x=substr('ABCDE',2,3); run; data d; length a b $2; a='XY'; b=reverse(a); c=a!!b; run;")
        self.assertEqual(result['datasets']['prior']['rows'],[{'x':'BCD  '}])
        self.assertEqual(result['datasets']['d']['rows'],[{'a':'XY','b':'YX','c':'XYYX'}])

    def test_catx_substr_items_trim_raw_and_stored_blanks(self):
        row=execute("data d; length a b $5; a=' aZ'; b='     '; x=catx(' / ',substr(a,2,3),substr(b,1,2),'Q'); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':' aZ  ','b':' '*5,'x':'aZ / Q'.ljust(200)})
        row=execute("data d; x=catx('|',substr('   ',1,2),substr('    ',2,2)); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':' '*200})

    def test_catx_accepts_dynamic_bounds_and_existing_target(self):
        row=execute("data d; length x $6; p=2; n=2; x=catx('|',substr('ABCDE',p,n),'Q'); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':'BC|Q  ','p':2.,'n':2.})

    def test_substr_of_fixed_reverse_and_concat_sources(self):
        table=execute("data d; length a $5; a='AB'; x=substr(reverse(a),3,2); y=substr(a!!'QZ',5,2); run;")['datasets']['d']
        self.assertEqual(table['schema']['x']['length'],5)
        self.assertEqual(table['schema']['y']['length'],7)
        self.assertEqual(table['rows'],[{'a':'AB   ','x':' B   ','y':' Q     '}])

    def test_recursive_fixed_sources_keep_value_width(self):
        row=execute("data d; a='AB '; x=substr(reverse(a!!'Q'),2,2); y=substr(reverse(a)!!'Q',2,3); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row,{'a':'AB ','x':' B  ','y':'BAQ '})

    def test_catx_substr_with_fixed_expression_source(self):
        row=execute("data d; a='AB '; x=catx('|',substr(reverse(a),2,2),substr(a!!'Q',3,2)); run;")['datasets']['d']['rows'][0]
        self.assertEqual(row['x'],'BA|Q'.ljust(200))

    def test_where_uses_input_descriptors_with_pdv_override(self):
        source="data d; length a $2; set raw; where substr(reverse(a),1,2)='  '; x=substr(a,1,1); r=reverse(x); run;"
        for rows in ([],[{'a':'AB'}]):
            inputs={'raw':{'schema':{'a':{'type':'character','length':4}},'rows':rows}}
            table=execute(source,inputs)['datasets']['d']
            self.assertEqual(table['schema']['x']['length'],2)
            self.assertEqual(table['rows'],[{'a':'AB','x':'A ','r':' A'}] if rows else [])
        source="data d; length a $4; set raw; where substr(a!!'Q',3,1)='Q'; run;"
        table=execute(source,{'raw':{'schema':{'a':{'type':'character','length':2}},'rows':[{'a':'AB'}]}})['datasets']['d']
        self.assertEqual(table['rows'],[{'a':'AB  '}])

    def test_empty_and_filtered_inputs_still_have_composed_schema(self):
        for rows,predicate in (([],''),([{'a':'AB'}],'where 0;')):
            table=execute("data d; set raw; "+predicate+" x=substr(a,1,1); r=reverse(x); c=x!!'Q'; z=catx('|',substr(a,1,1),'Q'); run;",
                          {'raw':{'schema':{'a':{'type':'character','length':4}},'rows':rows}})['datasets']['d']
            self.assertEqual(table['rows'],[])
            self.assertEqual([table['schema'][name]['length'] for name in ('x','r','c','z')],[4,4,5,200])

    def test_zero_trip_and_false_conditional_keep_schema(self):
        for body in ("do i=2 to 1; x=substr(reverse(a),2,1); z=catx('|',substr(a,1,1),'Q'); end;",
                     "if 0 then x=substr(reverse(a),2,1); if 0 then z=catx('|',substr(a,1,1),'Q');"):
            table=execute("data d; a='AB  '; "+body+" r=reverse(x); run;")['datasets']['d']
            self.assertEqual(table['schema']['x']['length'],4)
            self.assertEqual(table['rows'][0]['r'],' '*4)
            self.assertEqual(table['rows'][0]['z'],' '*200)

    def test_static_invalid_bounds_cannot_hide_in_empty_or_skipped_data(self):
        for expr in ("substr(reverse(a),5,1)","substr(a!!'Q',5,2)","catx('|',substr(a,0,1),'Q')", "catx('|',substr(a,1,'1'),'Q')"):
            for control in ('','do i=2 to 1;'):
                source='data d; set raw; '+control+' x='+expr+'; '+('end;' if control else '')+' run;'
                with self.subTest(expr=expr,control=control),self.assertRaises(ValueError):
                    execute(source,{'raw':{'schema':{'a':{'type':'character','length':4}},'rows':[]}})

    def test_wrong_source_descriptor_is_checked_without_rows(self):
        for expr in ("substr(reverse(a),1,1)","substr(a!!'Q',1,1)","catx('|',substr(a,1,1),'Q')"):
            with self.subTest(expr=expr),self.assertRaises(ValueError):
                execute('data d; set raw; x='+expr+'; run;',{'raw':{'schema':{'a':'number'},'rows':[]}})

    def test_width_sensitive_temporary_contexts_have_local_refusals(self):
        for expr in ("reverse(substr('ABCDE',2,3))", "substr('ABCDE',2,3)!!'Q'",
                     "catx(substr('ABCDE',2,1),'A','B')", "substr(substr('ABCDE',2,3),1,1)",
                     "lengthc(substr('ABCDE',2,3))", "substr(catx('|','A','B'),1,1)"):
            source='data d; x='+expr+'; run;';plan=compile_plan(source)
            self.assertTrue(plan.blocked,expr)
            self.assertNotIn('quarantin',str(plan.tickets))
            with self.assertRaisesRegex(ValueError,'SUBSTR|CATX'):
                run_plan(plan.to_dict(),allow_partial=True)

    def test_removed_ticket_metadata_does_not_bypass_local_refusal(self):
        for expr in ("reverse(substr('ABCDE',2,3))","'Q'!!substr('ABCDE',2,3)","catx(substr('AB',1,1),'Q')"):
            plan=compile_plan('data d; x='+expr+'; run;').to_dict();plan['tickets']=[];plan['matched']=[]
            with self.subTest(expr=expr),self.assertRaises(ValueError):run_plan(plan,allow_partial=True)

    def test_late_invalid_substr_bound_is_atomic_across_steps(self):
        self.check_atomic("data prior; put 'earlier'; run; data d; set raw; x=catx('|',substr(a,p,1),'Q'); put 'row'; output; run;",
                          [{'a':'AB','p':1},{'a':'AB','p':5}])

    def test_late_catx_capacity_failure_is_atomic(self):
        self.check_atomic("data prior; put 'earlier'; run; data d; length x $2; set raw; x=catx('|',substr(a,1,2),'Q'); put 'row'; run;",
                          [{'a':' ','p':1},{'a':'AB','p':1}])

    def check_atomic(self,source,rows):
        inputs={'raw':{'schema':{'a':{'type':'character','length':4},'p':'number'},'rows':rows}}
        printed=io.StringIO();ns={'inputs':inputs}
        with contextlib.redirect_stdout(printed),self.assertRaises(ValueError):exec(translate(source).code,ns)
        self.assertEqual(printed.getvalue(),'');self.assertNotIn('result',ns)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.json';path.write_text(json.dumps(inputs))
            with contextlib.redirect_stdout(printed):job=build_job(source,path)
        self.assertEqual(job.code,1);self.assertIsNone(job.result);self.assertFalse(job.receipt['accepted'])
        self.assertEqual(printed.getvalue(),'')

    def test_source_guards_and_target_limits_remain(self):
        for value in ('"&macro"',"'é'","'a\tb'"):
            source="data d; x=catx('|',substr('ABC',1,1),'Q'); unused="+value+'; run;'
            self.assertEqual(build_job(source).code,2)
        self.assertEqual(build_job("data _null_; x=substr('ABCDE',2,3); r=reverse(x); run;",target='cpp').code,2)
        self.assertEqual(build_job("data d; x=catx('|',substr('ABC',1,1),'Q'); put _all_; run;").code,1)


if __name__=='__main__':unittest.main()
