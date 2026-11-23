"""Counted LINK continuation, numeric bounds and portable validation."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import unittest

from saschi.emit_py import translate
from saschi.flow_control import COUNTED_LINK_PROFILE, LINK_PROFILE
from saschi.plan import compile_plan
from saschi.runtime import run_plan


CALLS = """data d;
do i=1 to 3;
    link mark;
    output;
end;
stop;
mark:
    if i=2 then do;
        value=20;
        return;
    end;
    value=i+10;
    return;
keep i value;
run;
"""

BOUND = """data d;
limit=9;
do i=2 to sqrt(limit);
    link change_limit;
    output;
end;
stop;
change_limit:
    limit=4;
    return;
keep i;
run;
"""


class CountedLinkTests(unittest.TestCase):
    def compiled(self, source):
        plan = compile_plan(source)
        self.assertFalse(plan.blocked, plan.tickets)
        portable = plan.to_dict()
        marker = portable['steps'][0]['operations'][0]
        self.assertEqual(marker['args']['name'], COUNTED_LINK_PROFILE)
        return portable

    def rows(self, source):
        return run_plan(self.compiled(source))['datasets']['d']['rows']

    def test_returns_resume_the_same_counted_body_and_keep_its_index(self):
        self.assertEqual(self.rows(CALLS), [
            {'i': 1., 'value': 11.}, {'i': 2., 'value': 20.}, {'i': 3., 'value': 13.},
        ])

    def test_sqrt_uses_captured_bound_on_both_sides_of_a_square(self):
        for limit, expected in ((8, [2.]), (9, [2., 3.]), (10, [2., 3.])):
            with self.subTest(limit=limit):
                self.assertEqual(self.rows(BOUND.replace('limit=9;', f'limit={limit};')),
                                 [{'i': value} for value in expected])
        descending = BOUND.replace('i=2 to sqrt(limit)', 'i=3 to sqrt(limit) by -1')
        self.assertEqual(self.rows(descending.replace('limit=9;', 'limit=8;')), [{'i': 3.}])
        self.assertEqual(self.rows(descending.replace('limit=9;', 'limit=4;')),
                         [{'i': 3.}, {'i': 2.}])

    def test_or_assigns_numeric_truth_from_both_comparisons(self):
        source = CALLS.replace('value=i+10;', 'value=i=1 or i=2;').replace('value=20;', 'value=i=1 or i=2;')
        self.assertEqual(self.rows(source), [
            {'i': 1., 'value': 1.}, {'i': 2., 'value': 1.}, {'i': 3., 'value': 0.},
        ])
        missing = CALLS.replace('value=i+10;', 'value=unseen=. or i=9;')
        result = run_plan(self.compiled(missing))
        self.assertEqual(result['datasets']['d']['rows'][0], {'i': 1., 'value': 1.})

    def test_stop_in_callee_finishes_the_step_with_prior_output(self):
        source = CALLS.replace('value=20;\n        return;', 'stop;') + 'data later;x=7;run;'
        result = run_plan(self.compiled(source))['datasets']
        self.assertEqual(result['d']['rows'], [{'i': 1., 'value': 11.}])
        self.assertEqual(result['later']['rows'], [{'x': 7.}])

    def test_separate_profile_refuses_wrong_call_context_and_callee_index_writes(self):
        for source in (
            CALLS.replace('link mark;', 'if i=1 then link mark;'),
            CALLS.replace('value=i+10;', 'i=10;'),
            CALLS.replace('value=i+10;', 'do i=1 to 2;value=i;end;'),
            CALLS.replace('value=i+10;', 'do j=1 to 2;link mark;end;'),
            CALLS.replace('link mark;', 'link mark; return;'),
            BOUND.replace('sqrt(limit)', 'sqrt(i)'),
            BOUND.replace('sqrt(limit)', 'sqrt(-1)'),
        ):
            with self.subTest(source=source):
                self.assertTrue(compile_plan(source).blocked)
        portable = self.compiled(CALLS)
        portable['steps'][0]['operations'][0]['args']['name'] = LINK_PROFILE
        with self.assertRaisesRegex(ValueError, 'LINK requires a top-level'):
            run_plan(portable)

    def test_portable_sqrt_and_comparison_fields_are_checked(self):
        plan = self.compiled(BOUND)
        malformed = deepcopy(plan)
        loop = next(op for op in malformed['steps'][0]['operations'] if op['kind'] == 'do_counted')
        loop['args']['stop']['args'].append({'kind': 'number', 'value': 9})
        with self.assertRaisesRegex(ValueError, 'SQRT stop requires exactly one argument'):
            run_plan(malformed)

        source = CALLS.replace('value=i+10;', 'value=i=1 or i=3;')
        plan = self.compiled(source)
        assignment = next(op for op in plan['steps'][0]['operations'] if op['kind'] == 'flow_or_assign')
        assignment['args']['conditions'][0] = {'op': 'truth', 'left': {'kind': 'number', 'value': 1}}
        with self.assertRaisesRegex(ValueError, 'OR assignment requires two numeric comparisons'):
            run_plan(plan)

    def test_late_invalid_sqrt_discards_earlier_emitted_stdout(self):
        source = ('data early;x=1;put x;run;'
                  + CALLS.replace('value=i+10;', 'do j=1 to sqrt(2-i);value=j;end;'))
        translated = translate(source)
        self.assertFalse(translated.blocked, translated.tickets)
        stream = io.StringIO()
        namespace = {}
        with redirect_stdout(stream), self.assertRaisesRegex(ValueError, 'nonnegative radicand'):
            exec(translated.code, namespace)
        self.assertEqual(stream.getvalue(), '')
        self.assertNotIn('result', namespace)
