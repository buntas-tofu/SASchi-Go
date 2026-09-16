"""Original typed metadata witnesses motivated by Garage SL006 and SL020."""
import copy
import json
import unittest
from .test_plan import execute
from .compare import table_equal
from .plan import compile_plan
from sas_semantics import sas_fixed_character, sas_numeric_order


class MetadataTests(unittest.TestCase):
    def catalog(self):
        return {'a': {'encoding':'utf-8', 'label':'Original transport label', 'schema':{
            'id':{'type':'character', 'length':3, 'label':'Identifier', 'format':'$3.'},
            'day':{'type':'number', 'length':8, 'format':'DATE9.', 'label':'Day'},
            'value':{'type':'number', 'label':'Reading'},
            'text':{'type':'character','length':4}},
            'rows':[{'id':'007','day':0,'value':{'missing':'A'},'text':'éé'},
                    {'id':'002','day':1,'value':None,'text':'北 '}]}}

    def test_metadata_survives_execution_and_json_roundtrip(self):
        catalog = self.catalog(); before = copy.deepcopy(catalog)
        result = execute('data d; set a; output; run;', catalog)['datasets']['d']
        self.assertTrue(table_equal(result, catalog['a']))
        roundtrip = json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
        self.assertTrue(table_equal(result, roundtrip))
        self.assertEqual(catalog, before)
        result['rows'][0]['value']['missing'] = 'B'
        self.assertEqual(catalog, before)

    def test_sort_preserves_metadata_and_leading_zero_identifier(self):
        catalog = self.catalog()
        result = execute('proc sort data=a out=d; by id; run;', catalog)['datasets']['d']
        self.assertEqual([r['id'] for r in result['rows']], ['002', '007'])
        self.assertEqual(result['schema'], catalog['a']['schema'])
        self.assertEqual(result['encoding'], 'utf-8')

    def test_character_width_is_consumed_by_assignment(self):
        short = execute("data d; code='Q'; code='WXYZ'; run;")['datasets']['d']
        self.assertEqual(short['rows'], [{'code':'W'}])
        wide = execute("data d; length code $ 5; code='Q'; code='WXYZ'; run;")['datasets']['d']
        self.assertEqual(wide['rows'], [{'code':'WXYZ '}])
        self.assertEqual(wide['schema']['code'], {'type':'character','length':5})
        self.assertTrue(compile_plan("data d; code='Q'; length code $ 5; run;").blocked)

    def test_literal_width_and_quotes(self):
        result = execute('data d; x="a\'b"; y=\'a"b\'; z=\'it\'\'s\'; run;')['datasets']['d']
        self.assertEqual(result['rows'], [{'x':"a'b", 'y':'a"b', 'z':"it's"}])
        self.assertEqual(result['schema']['z']['length'], 4)

    def test_character_copy_gets_width_but_no_inherited_label(self):
        result = execute('data d; set a; copied=id; run;', self.catalog())['datasets']['d']
        self.assertEqual(result['schema']['copied'], {'type':'character','length':3})
        self.assertEqual([r['copied'] for r in result['rows']], ['007', '002'])

    def test_multibyte_assignment_has_explicit_boundary(self):
        self.assertEqual(sas_fixed_character('éé', 2), 'é')
        self.assertEqual(sas_fixed_character('北', 4), '北 ')
        with self.assertRaisesRegex(ValueError, 'code point'):
            execute("data d; length x $ 1; x='é'; run;")
        with self.assertRaisesRegex(ValueError, 'code point'):
            sas_fixed_character('北', 4, 'latin-1')

    def test_tagged_missing_order_and_identity(self):
        values = [3., {'missing':'Z'}, None, {'missing':'A'}, {'missing':'_'}, -4.]
        catalog = {'a':{'schema':{'x':'number'},'rows':[{'x':v} for v in values]}}
        result = execute('proc sort data=a out=d; by x; run;', catalog)['datasets']['d']
        self.assertEqual([r['x'] for r in result['rows']], [{'missing':'_'}, None, {'missing':'A'}, {'missing':'Z'}, -4., 3.])
        self.assertEqual(sorted(values, key=sas_numeric_order), [r['x'] for r in result['rows']])
        actual = execute('data d; a=.A; b=._; c=round(a,1); if b < a then flag=1; run;')['datasets']['d']['rows']
        self.assertEqual(actual, [{'a':{'missing':'A'}, 'b':{'missing':'_'}, 'c':None, 'flag':1.}])

    def test_character_comparison_pads_blanks(self):
        result = execute("data d; length x $ 4; x='ab'; if x='ab' then flag=1; run;")['datasets']['d']['rows']
        self.assertEqual(result, [{'x':'ab  ', 'flag':1.}])
        self.assertEqual(execute("data d; x=''; if x < '\t' then flag=1; run;")['datasets']['d']['rows'][0]['flag'], None)

    def test_invalid_input_types_tags_and_widths_fail(self):
        for value in [True, '1', {'missing':'a'}, {'missing':'AA'}, {'missing':'.'}, float('inf'), 10**500]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                execute('data d; set a; run;', {'a':{'schema':{'x':'number'}, 'rows':[{'x':value}]}})
        for width in (True, 0, -1, 32768):
            with self.assertRaises(ValueError):
                execute('data d; set a; run;', {'a':{'schema':{'x':{'type':'character','length':width}},'rows':[]}})
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            execute('data d; set a; run;', {'a':{'schema':{'x':{'type':'character','length':1}},'rows':[{'x':'long'}]}})

    def test_type_conversion_and_mixed_encodings_require_review(self):
        for source in ("data d; x=1; x='a'; run;", "data d; x='a'; y=round(x,1); run;", "data d; x='a'; if x=1 then y=1; run;"):
            with self.assertRaises(ValueError): execute(source)
        catalog = self.catalog(); catalog['cfg'] = dict(catalog['a'], encoding='latin-1', rows=[])
        with self.assertRaisesRegex(ValueError, 'encoding'):
            execute('data d; if _n_=1 then set cfg; set a; run;', catalog)

    def test_empty_output_keeps_every_descriptor(self):
        catalog = self.catalog()
        result = execute('data d; set a; if 0 then output; run;', catalog)['datasets']['d']
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['schema'], catalog['a']['schema'])
        for field in ('encoding', 'label'): self.assertEqual(result[field], catalog['a'][field])

    def test_malformed_catalog_is_a_validation_error(self):
        for catalog in ([], {'a':[]}, {'a':{'schema':{},'rows':{}}},
                        {'a':{'schema':{'x':'number'},'rows':[[]]}},
                        {'a':{'schema':{'_n_':'number'},'rows':[]}}):
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                execute('data d; set a; run;', catalog)

    def test_by_key_truncation_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'BY key width'):
            execute('data d; length id $ 1; set a; by id; run;',
                    {'a':{'schema':{'id':{'type':'character','length':3}},'rows':[{'id':'001'}]}})

    def test_merge_input_reassignment_requires_review(self):
        catalog = {n:{'schema':{'id':'number','x':'number'},'rows':[{'id':1,'x':2}]} for n in ('a','b')}
        with self.assertRaisesRegex(ValueError, 'merge-event'):
            execute('data d; merge a b; by id; x=x+1; run;', catalog)
