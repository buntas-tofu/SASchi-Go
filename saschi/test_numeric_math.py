"""Source, portable and state boundaries for the opt-in numeric math profile."""
from copy import deepcopy
from decimal import Decimal, localcontext
import contextlib
import io
import math
from pathlib import Path
import sys
import unittest

from saschi import binary64, numeric_math
from saschi.arrays import ARRAY_RESERVED
from saschi.emit_cpp import translate as cpp
from saschi.emit_py import translate
from saschi.functions import FUNCTIONS, BINARY64_FUNCTIONS
from saschi.job import build_job
from saschi.plan import compile_plan, expression
from saschi.runtime import run_plan

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / 'examples/numeric_math_capture.sas'


def execute(source, catalog=None, emitted=False):
    parsed = compile_plan(source)
    if parsed.blocked:
        raise ValueError(str(parsed.tickets))
    plan = parsed.to_dict();saved = deepcopy(plan)
    result = run_plan(plan, catalog)
    assert plan == saved
    if emitted:
        scope = {'inputs':deepcopy(catalog or {})};stream = io.StringIO()
        with contextlib.redirect_stdout(stream):exec(translate(source).code, scope)
        assert scope['result'] == result
        assert stream.getvalue() == ''.join(line+'\n' for line in result['log'])
    return result


def inline(records, body='y=log(x);'):
    return 'data d;input x;'+body+'datalines;\n'+''.join(x+'\n' for x in records)+';\nrun;'


class NumericMathTests(unittest.TestCase):
    def refuses(self, source):
        with self.assertRaises(ValueError):execute(source)

    def test_unary_high_precision_values_and_missing(self):
        for name, values in [('sqrt',[0.,1.,2.,4.,binary64.LIMIT,sys.float_info.min]),('log',[1.,2.,.5,binary64.LIMIT,sys.float_info.min,math.nextafter(1.,2.),math.nextafter(1.,0.)])]:
            self.assertIsNone(numeric_math.apply(name,[None]))
            for x in values:
                with localcontext() as c:
                    c.prec=90;d=Decimal.from_float(x);truth=float(d.sqrt() if name=='sqrt' else d.ln())
                actual=numeric_math.apply(name,[x])
                self.assertLessEqual(abs(actual-truth),32*sys.float_info.epsilon*max(1.,abs(truth)))

    def test_unary_argument_types_ranges_and_arity(self):
        for name in ('sqrt','log'):
            for value in (True,'4',{'missing':'A'},math.inf,math.nan,2147483648.,5e-324):
                with self.assertRaises(ValueError):numeric_math.apply(name,[value])
            for values in ([],[1.,2.]):
                with self.assertRaises(ValueError):numeric_math.apply(name,values)
        for name,value in [('sqrt',-1.),('log',0.),('log',-1.)]:
            with self.assertRaises(ValueError):numeric_math.apply(name,[value])

    def test_SUM_order_all_missing_and_eager_invalid_values(self):
        self.assertIsNone(numeric_math.apply('sum',[None,None]))
        self.assertEqual(numeric_math.apply('sum',[None,0.]),0.)
        self.assertEqual(numeric_math.apply('sum',[1e9,.1,-1e9]),.10000002384185791)
        for values in ([None,2147483648.],[binary64.LIMIT,1.,-1.],[None,True]):
            with self.assertRaises(ValueError):numeric_math.apply('sum',values)

    def test_SUM_argument_boundaries_source_and_direct(self):
        self.assertEqual(numeric_math.apply('sum',[1.]*1024),1024.)
        for size in (0,1025):
            with self.assertRaises(ValueError):numeric_math.apply('sum',[1.]*size)
        good='data d;t=1**1;s=sum('+','.join(['1']*1024)+');run;'
        self.assertEqual(execute(good)['datasets']['d']['rows'][0]['s'],1024.)
        self.refuses(good.replace('sum(1,','sum(1,1,',1))

    def test_profile_selection_is_per_step_and_plain_SUM_shape_unchanged(self):
        p=compile_plan('data a;t=1**1;run;data b;x=sum(1,2);run;').to_dict()
        self.assertEqual(p['steps'][0]['operations'][0]['args']['name'],binary64.PROFILE)
        self.assertEqual(p['steps'][1]['operations'][0]['kind'],'assign')
        p=compile_plan('data d;t=1**1;x=sum(1,2);run;').to_dict()
        self.assertEqual(p['steps'][0]['operations'][0]['args']['name'],numeric_math.PROFILE)
        self.assertIsNone(expression('sqrt(4)'))

    def test_names_strings_and_opaque_headers_are_not_math_triggers(self):
        cases=['data d;sqrt=4;log=2;run;',"data _null_;put 'sqrt(4);log(2)';run;",
               'data d;array sqrt{1} x;x=4;y=sqrt{1};run;',
               'data d;array log{1} x;x=4;y=log[1];run;',
               'data d;array sqrt{1} x;x=4;y=sum(of sqrt(*));run;']
        for source in cases:
            p=compile_plan(source);self.assertFalse(p.blocked,p.tickets)
            self.assertFalse(numeric_math.has_marker(p.to_dict()))
        header="data d;infile datalines dlm=',' firstobs=2;input x1-x2;datalines;\nsqrt(4),log(2)\n1,2\n;\nrun;"
        self.assertFalse(numeric_math.has_marker(compile_plan(header).to_dict()))

    def test_function_array_ambiguity_stays_refused(self):
        self.refuses('data d;array sqrt{2} a b;a=4;b=9;y=sqrt(1);run;')
        self.refuses('data d;array log{2} a b;a=4;b=9;y=log(1);run;')

    def test_global_function_and_array_registries_remain_old(self):
        self.assertNotIn('sqrt',FUNCTIONS);self.assertNotIn('log',FUNCTIONS)
        self.assertNotIn('sqrt',BINARY64_FUNCTIONS);self.assertNotIn('log',binary64.CALLS)
        self.assertNotIn('sqrt',ARRAY_RESERVED);self.assertNotIn('log',ARRAY_RESERVED)

    def test_old_markers_and_unmarked_forged_calls_refuse(self):
        original=compile_plan('data d;x=sqrt(4);run;').to_dict()
        for marker in (binary64.PROFILE,binary64.ROWS_PROFILE,'binary64-pipeline-v1'):
            p=deepcopy(original);p['steps'][0]['operations'][0]['args']['name']=marker
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['operations'].pop(0)
        with self.assertRaises(ValueError):run_plan(p)

    def test_math_marker_without_its_own_trigger_refuses(self):
        p=compile_plan('data d;x=sqrt(4);run;').to_dict();p['steps'][0]['operations'][-1]['args']['value']={'kind':'number','value':2.}
        with self.assertRaises(ValueError):run_plan(p)
        p['steps'][0]['display_names']['fake']={'kind':'call','name':'sqrt','args':[{'kind':'number','value':4.}]}
        with self.assertRaises(ValueError):run_plan(p)

    def test_literal_domains_validate_dead_empty_and_zero_trip_paths(self):
        for body in ('if 0 then y=log(0);','if 0 then y=sqrt(-1);','do while(0);y=log(0);end;'):
            self.refuses(inline([],body))
        for source in ('data d;y=sqrt(2147483648);run;','data d;y=log(2147483648);run;','data d;y=sum(.,2147483648);t=1**1;run;'):
            self.refuses(source)

    def test_dynamic_domains_remain_lazy_when_skipped(self):
        result=execute(inline(['0'],'if 0 then y=log(x);'))
        self.assertIsNone(result['datasets']['d']['rows'][0]['y'])
        self.refuses(inline(['1','0']))

    def test_nested_calls_round_inputs_before_functions(self):
        row=execute('data d;x=log(1+0.00000000000000001);y=sqrt(sum(1,3));run;',emitted=True)['datasets']['d']['rows'][0]
        self.assertEqual(row,{'x':0.,'y':2.})
        self.refuses('data d;x=sqrt(1e-200*1e-200);run;')

    def test_tiny_valid_log_result_keeps_old_PUT_refusal(self):
        source='data d;x=log(1.0000000000000002);run;'
        self.assertGreater(execute(source)['datasets']['d']['rows'][0]['x'],0.)
        self.refuses(source.replace('run;','put x;run;'))

    def test_exact_indices_and_counted_controls_do_not_gain_functions(self):
        for source in ('data d;array a{2} x y;t=log(1);a{sqrt(1)}=2;run;',
                       'data d;t=log(1);do i=1 to sqrt(4);x=i;end;run;'):
            self.refuses(source)

    def test_existing_input_conversion_is_not_widened(self):
        self.refuses(inline(['0.1'],'y=sqrt(x);'))
        self.assertEqual(execute(inline(['.5'],'y=sqrt(x);'))['datasets']['d']['rows'][0]['x'],.5)

    def test_FILE_comma_input_and_flow_frontiers_remain_refused(self):
        self.refuses('data _null_;file "a.csv" dlm=\',\';x=sqrt(4);put x;run;')
        self.refuses("data d;infile datalines dlm=',';input x1-x2;y=sqrt(x1);datalines;\n1,2\n;\nrun;")
        self.refuses('data d;x=sqrt(4);stop;run;')

    def test_scalar_SET_math_preserves_descriptors_and_caller(self):
        catalog={'raw':{'encoding':'ascii','label':'input','schema':{'x':{'type':'number','length':8,'label':'X'}},'rows':[{'x':4.},{'x':None}]}}
        saved=deepcopy(catalog);result=execute('data d;set raw;y=sqrt(x);run;',catalog,True)
        self.assertEqual(catalog,saved);self.assertEqual(result['datasets']['d']['schema']['x'],catalog['raw']['schema']['x'])
        self.assertEqual([r['y'] for r in result['datasets']['d']['rows']],[2.,None])

    def test_selected_unused_bad_values_and_empty_descriptors_refuse(self):
        for rows in ([],[{'x':1.,'bad':2147483648.}]):
            schema={'x':'number','bad':{'type':'number','length':4} if not rows else 'number'}
            with self.assertRaises(ValueError):execute('data d;set raw;y=log(x);run;',{'raw':{'schema':schema,'rows':rows}})

    def test_original_snapshots_retained_state_and_fresh_reset(self):
        result=execute(ORIGINAL.read_text(),emitted=True);rows=result['datasets']['transformed']['rows']
        self.assertEqual(len(rows),6);self.assertEqual([r['stage'] for r in rows],[1.,2.]*3)
        self.assertEqual([r['seq'] for r in rows],[1.,1.,2.,2.,3.,3.])
        self.assertEqual(rows[4]['running'],rows[2]['running']);self.assertIsNone(rows[4]['combined']);self.assertIsNone(rows[4]['array_total'])
        self.assertEqual(result['datasets']['fresh']['rows'],[{'root':2.,'logged':0.,'combined':2.,'running':2.}])

    def test_implicit_current_alias_math_is_evaluated_in_active_binding(self):
        source='data d;array a x y;x=4;y=9;do over a;a=sqrt(a);output;end;run;'
        self.assertEqual([(r['x'],r['y']) for r in execute(source)['datasets']['d']['rows']],[(2.,9.),(2.,3.)])
        with self.assertRaises(ValueError):numeric_math.array_current_set({'name':'a','value':{'kind':'number','value':1.}},{},{'a':{'names':['x']}},{})

    def test_late_failure_discards_prior_step_and_buffered_stdout(self):
        source='data earlier;x=1;put x;run;'+inline(['1','0'])
        job=build_job(source);self.assertFalse(job.receipt['accepted']);self.assertIsNone(job.result)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{})
        self.assertEqual(stream.getvalue(),'')

    def test_version_marker_extra_fields_and_predicate_shapes(self):
        original=compile_plan(inline([])).to_dict()
        for value in (True,2.,'2',None):
            p=deepcopy(original);p['version']=value
            with self.assertRaises(ValueError):run_plan(p)
        p=deepcopy(original);p['steps'][0]['extra']='ignored'
        with self.assertRaises(ValueError):run_plan(p)
        for name in ([],{},None,True):
            p=deepcopy(original);p['steps'][0]['operations'][-1]['args']['value']['name']=name
            with self.assertRaises(ValueError):run_plan(p)

    def test_cycles_and_nested_markers_refuse_before_recursion(self):
        p=compile_plan('data d;x=sqrt(4);run;').to_dict();value=p['steps'][0]['operations'][-1]['args']['value'];value['args']=[value]
        with self.assertRaises(ValueError):run_plan(p)
        p=compile_plan('data d;x=1;run;').to_dict();value=p['steps'][0]['operations'][-1]['args']['value'];value['cycle']=value
        with self.assertRaises(ValueError):run_plan(p)
        p=compile_plan('data d;x=sqrt(4);run;').to_dict();p['steps'][0]['operations'].append(deepcopy(p['steps'][0]['operations'][0]))
        with self.assertRaises(ValueError):run_plan(p)

    def test_node_depth_and_deep_source_fail_controlled(self):
        self.refuses('data d;y='+('sqrt('*1000)+'4'+(')'*1000)+';run;')
        self.refuses('data d;x=sqrt(4);y='+'+'.join(['x']*130)+';run;')

    def test_legacy_large_portable_plan_keeps_prior_admission(self):
        p=compile_plan('data d;x=1;run;').to_dict();op=p['steps'][0]['operations'][0];p['steps'][0]['operations']=[deepcopy(op) for _ in range(20001)];saved=deepcopy(p)
        self.assertEqual(run_plan(p)['datasets']['d']['rows'],[{'x':1.}]);self.assertEqual(p,saved)

    def test_CPP_refuses_new_operation_with_scalar_NULL_destination(self):
        result=cpp('data _null_;x=sqrt(4);run;');self.assertTrue(result.blocked)
        self.assertTrue(any(t.construct=='cpp-target' and 'operation' in t.reason for t in result.tickets))


if __name__=='__main__':unittest.main()
