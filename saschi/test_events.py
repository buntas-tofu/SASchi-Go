"""Original event witnesses motivated by Garage SL003, SL004, SL005."""
import copy
import unittest
from .test_plan import execute, table
from .plan import compile_plan
from .emit_py import translate
from .emit_cpp import translate as cpp_translate


class EventTests(unittest.TestCase):
    def test_output_snapshots_and_suppression(self):
        result = execute('data d; x=13; output; x=29; output d; x=47; run;')['datasets']['d']
        self.assertEqual(result['rows'], [{'x':13.}, {'x':29.}])
        self.assertNotEqual(result['rows'], [{'x':47.}])
        self.assertEqual(execute('data d; x=13; if 0 then output; run;')['datasets']['d']['rows'], [])

    def test_output_before_rejection_survives(self):
        rows = execute('data d; x=13; output; if 0; x=29; output; run;')['datasets']['d']['rows']
        self.assertEqual(rows, [{'x':13.}])

    def test_no_implicit_output_per_input_row(self):
        catalog = {'a': table([{'x':1}, {'x':2}, {'x':3}])}
        rows = execute('data d; set a; if x=2 then output; run;', catalog)['datasets']['d']['rows']
        self.assertEqual(rows, [{'x':2.}])

    def test_where_precedes_by_if_follows_by(self):
        catalog = {'a': table([{'g':7,'keep':0}, {'g':7,'keep':1}, {'g':9,'keep':1}])}
        source = 'data d; set a; by g; FILTER keep=1; f=first.g; l=last.g; n=_n_; run;'
        where = execute(source.replace('FILTER', 'where'), catalog)['datasets']['d']['rows']
        subset = execute(source.replace('FILTER', 'if'), catalog)['datasets']['d']['rows']
        self.assertEqual([r['f'] for r in where], [1., 1.])
        self.assertEqual([r['f'] for r in subset], [0., 1.])
        self.assertEqual([r['n'] for r in where], [1., 2.])
        self.assertEqual([r['n'] for r in subset], [2., 3.])
        self.assertEqual([r['l'] for r in where], [1., 1.])

    def test_where_uses_input_not_assignment(self):
        catalog = {'a': table([{'x':1}, {'x':2}])}
        rows = execute('data d; set a; x=9; where x=1; run;', catalog)['datasets']['d']['rows']
        self.assertEqual(rows, [{'x':9.}])
        for predicate in ('_n_=1', 'first.x=1', 'created=1'):
            with self.assertRaisesRegex(ValueError, 'WHERE'):
                execute(f'data d; set a; created=1; where {predicate}; run;', catalog)

    def test_by_prefix_flags_and_group_reset(self):
        catalog = {'a': table([{'g':1,'h':5,'x':2}, {'g':1,'h':5,'x':3}, {'g':2,'h':5,'x':7}])}
        rows = execute('data d; set a; by g h; retain total 0; if first.g then total=0; total=total+x; f=first.h; l=last.h; run;', catalog)['datasets']['d']['rows']
        self.assertEqual([r['total'] for r in rows], [2., 5., 7.])
        self.assertEqual([r['f'] for r in rows], [1., 0., 1.])
        self.assertEqual([r['l'] for r in rows], [0., 1., 1.])

    def test_retained_input_and_scratch_have_different_lifetimes(self):
        catalog = {'cfg':table([{'fee':6}, {'fee':100}]), 'a':table([{'x':2}, {'x':4}, {'x':8}])}
        before = copy.deepcopy(catalog)
        source = 'data d; retain total 0; if _n_=1 then set cfg; set a; total=total+x; if _n_=1 then scratch=17; fee=fee+1; output; run;'
        rows = execute(source, catalog)['datasets']['d']['rows']
        self.assertEqual([r['fee'] for r in rows], [7., 8., 9.])
        self.assertEqual([r['total'] for r in rows], [2., 6., 14.])
        self.assertEqual([r['scratch'] for r in rows], [17., None, None])
        self.assertEqual(catalog, before)
        namespace = {'inputs':catalog}
        exec(translate(source).code, namespace)
        self.assertEqual(namespace['result']['datasets']['d']['rows'], rows)
        self.assertEqual(list(namespace['result']['datasets']['d']['schema']), ['total', 'fee', 'x', 'scratch'])

    def test_retention_survives_subsetting_rejection(self):
        catalog = {'a':table([{'x':2}, {'x':4}])}
        rows = execute('data d; retain total 0; set a; total=total+x; if x=4; run;', catalog)['datasets']['d']['rows']
        self.assertEqual(rows, [{'total':6., 'x':4.}])

    def test_driver_overwrites_overlapping_lookup_value(self):
        catalog = {'cfg':table([{'x':100}]), 'a':table([{'x':2}, {'x':4}])}
        rows = execute('data d; if _n_=1 then set cfg; set a; x=x+1; run;', catalog)['datasets']['d']['rows']
        self.assertEqual(rows, [{'x':3.}, {'x':5.}])

    def test_empty_sources_preserve_schema(self):
        catalog = {'cfg':{'schema':{'fee':'number'},'rows':[]}, 'a':table([{'x':2}])}
        actual = execute('data d; if _n_=1 then set cfg; set a; output; run;', catalog)['datasets']['d']
        self.assertEqual(actual, {'schema':{'fee':'number','x':'number'},'rows':[]})
        catalog['cfg']['rows'] = [{'fee':6}]; catalog['a']['rows'] = []
        self.assertEqual(execute('data d; if _n_=1 then set cfg; set a; run;', catalog)['datasets']['d']['rows'], [])

    def test_sorted_by_required_and_unknown_flags_rejected(self):
        with self.assertRaisesRegex(ValueError, 'sorted'):
            execute('data d; set a; by x; run;', {'a':table([{'x':2}, {'x':1}])})
        with self.assertRaisesRegex(ValueError, 'FIRST/LAST'):
            execute('data d; x=first.g; run;')

    def test_bounded_syntax_and_targets(self):
        sources = ['data d e; x=1; output d; run;', 'data d; output elsewhere; run;',
                   'data d; if 0 then output elsewhere; run;', 'data d; retain x; run;',
                   'data d; if 1 then do; x=2; end; run;', 'data d; where x=1; run;',
                   'data d; if _n_=1 then set a; run;', 'data d; _n_=5; run;',
                   'data d; x=1; set a; run;']
        for source in sources:
            with self.subTest(source=source): self.assertTrue(compile_plan(source).blocked)
        for body in ('output', 'if 1 then x=2', 'retain x 0', 'x=_n_', 'put _n_=', 'x=.A', "x='ab'", 'x=x+1'):
            with self.subTest(body=body): self.assertTrue(cpp_translate(f'data _null_; {body}; run;').blocked)

    def test_automatic_variables_do_not_leak(self):
        actual = execute('data d; x=_n_; put _n_=; run;')
        self.assertEqual(actual['datasets']['d'], {'schema':{'x':'number'},'rows':[{'x':1.}]})
        self.assertEqual(actual['log'], ['_n_=1'])

    def test_version_one_program_remains_executable(self):
        from .runtime import run_plan
        plan = compile_plan('data d; set a; x=round(x,1); run;').to_dict()
        plan['version'] = 1
        plan['steps'][0]['operations'] = [op for op in plan['steps'][0]['operations'] if op['kind'] != 'read']
        self.assertEqual(run_plan(plan, {'a':table([{'x':2.5}])})['datasets']['d']['rows'], [{'x':3.}])
