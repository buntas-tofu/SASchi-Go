"""Boundaries and publication behavior for the separate date source family."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from .plan import compile_plan
from .runtime import run_plan
from .emit_cpp import translate as cpp_translate
from .job import build_job
from . import date_program as dates

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/date_profile.sas').read_text()
EXPECTED=json.loads((ROOT/'examples/date_profile_expected.json').read_text())


def plan(text=SOURCE):
    value=compile_plan(text)
    if value.blocked:raise AssertionError(value.tickets)
    return value.to_dict()


def producer(records, *, columns='d :date9.', name='extra'):
    return f'data {name};\ninfile cards;\ninput {columns};\ncards;\n'+('\n'.join(records)+'\n' if records else '')+';\nrun;\n'


def late_failure():
    return (SOURCE+producer(['01JAN2000 '*3+'01JAN2000'],columns='a :date9. b :date9. c :date9. d :date9.',name='wide')
            +"proc format;value usr_long low-high='"+'X'*128+"';run;\n"
            +'proc print data=wide;format a b c d usr_long.;run;\n')


class DateProgramTests(unittest.TestCase):
    def refuse(self,text):
        value=compile_plan(text)
        self.assertTrue(value.blocked,text)
        self.assertFalse(build_job(text).receipt['accepted'])

    def test_complete_original_typed_ordered_storage_and_report(self):
        result=run_plan(plan());self.assertEqual(result,EXPECTED)
        self.assertEqual(list(result['datasets']['dates']['schema']),['id','sex','amount','born','hired'])
        self.assertIs(type(result['datasets']['dates']['rows'][0]['born']),float)

    def test_data_only_keeps_numeric_dates_without_report(self):
        text=SOURCE.split('proc format;',1)[0]
        self.assertEqual(run_plan(plan(text)),{'datasets':EXPECTED['datasets'],'log':[]})

    def test_two_report_snapshots_and_title_reset(self):
        suffix='proc print data=dates;format born hired cohort.;run;\n'
        result=run_plan(plan(SOURCE+suffix))
        self.assertEqual(result['reports']['print_01.txt'],EXPECTED['reports']['print_01.txt'])
        self.assertEqual(result['reports']['print_02.txt'],EXPECTED['reports']['print_01.txt'].split('\n',1)[1])

    def test_four_digit_literals_and_case_variants(self):
        value=SOURCE.replace("'31DEC1959'd",'"31dec1959"D').replace('weekdate37','WEEKDATE29').replace('worddate20','WORDDATE18')
        self.assertEqual(run_plan(plan(value)),EXPECTED)

    def test_format_literal_quotes_are_escaped_as_json(self):
        value=SOURCE.replace("'New era'", '"It\'s new"')
        self.assertIn('"It\'s new"',run_plan(plan(value))['reports']['print_01.txt'])
        value=SOURCE.replace("'New era'","'It''s new'")
        self.assertIn('"It\'s new"',run_plan(plan(value))['reports']['print_01.txt'])

    def test_input_refusals_are_eager_even_without_reports(self):
        base=SOURCE.split('proc format;',1)[0]
        for old,new in [('31DEC1959','31FEB1959'),('31DEC1959','31DEC59'),('31DEC1959','1959-12-31'),
                        ('31DEC1959','.A'),('F 7','FF 7'),('F 7','. 7'),('F 7','F 1.5'),
                        ('F 7','F 2147483648'),('F 7','F 1e2'),('31DEC1959 01JAN1960','31DEC1959'),
                        ('31DEC1959 01JAN1960','31DEC1959 01JAN1960 extra'),('31DEC1959','01JAN1752'),
                        ('31DEC1959','01JAN4000'),('F 7','é 7')]:
            with self.subTest(new=new):self.refuse(base.replace(old,new))

    def test_source_forms_outside_the_profile_refuse(self):
        for old,new in [('infile cards','infile cards dsd'),('infile cards','infile datalines'),
                        ('input id','input @1 id'),('input id','input id :8.'),
                        ('data dates','data dates(drop=id)'),('sex :$1.','sex $1.'),
                        ('proc print data=dates','proc print data=dates noobs'),
                        ('format born hired cohort.','format id cohort.'),
                        ('format born hired cohort.','format born born cohort.'),
                        ('format born hired cohort.','format absent cohort.'),
                        ('format born hired cohort.','format born hired absent.'),
                        ('proc format','proc format library=work'),('value cohort','value worddate'),
                        ('value cohort','value arbitrary'),('value cohort','value usr_bad1'),
                        ("'31DEC1959'd","'31DEC59'd"),('run;\ntitle;', 'run;\noptions nodate;\ntitle;')]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))

    def test_unsupported_widths_refuse_unused_and_empty_definitions(self):
        data=producer([])
        for output in ('[weekdate50.]','[weekdate28.]','[worddate17.]','[worddate33.]','[cohort.]'):
            with self.subTest(output=output):self.refuse(data+'proc format;value cohort low-high='+output+';run;')

    def test_range_holes_overlaps_order_and_literal_controls_refuse(self):
        for old,new in [("'01JAN1960'd","'02JAN1960'd"),("'01JAN1960'd","'31DEC1959'd"),
                        ("low-","'01JAN1754'd-"),("-high=","-'31DEC3998'd="),
                        ("'New era'","''"),("'New era'","' New era'"),("'New era'","'New era '"),
                        ("'New era'","'&value'"),("'New era'","'é'"),("'New era'","'"+'X'*129+"'")]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))

    def test_duplicate_names_and_unqualified_composition_refuse(self):
        for suffix in [SOURCE,producer([],name='dates'),"proc format;value cohort low-high='X';run;",
                       'data unused;set dates;run;','proc sort data=dates out=sorted;by id;run;',
                       'proc means data=dates;run;']:
            with self.subTest(suffix=suffix):self.refuse(SOURCE+suffix)

    def test_descriptor_width_storage_and_unformatted_dates(self):
        value=SOURCE.replace('sex :$1.','sex :$3.').replace('format born hired cohort.','format born cohort.')
        result=run_plan(plan(value));row=result['datasets']['dates']['rows'][0]
        self.assertEqual(row['sex'],'F  ');self.assertEqual(row['hired'],0.)
        self.assertIn('"Thursday, December 31, 1959" 0\n',result['reports']['print_01.txt'])

    def test_component_upper_bounds_and_excess(self):
        text=producer(['.']*1000);self.assertEqual(len(run_plan(plan(text))['datasets']['extra']['rows']),1000)
        self.refuse(producer(['.']*1001))
        columns='d :date9. '+' '.join('c'+str(i) for i in range(31))
        self.assertEqual(len(run_plan(plan(producer([],columns=columns)))['datasets']['extra']['schema']),32)
        self.refuse(producer([],columns=columns+' overflow'))
        for width in (0,65):self.refuse(producer([],columns=f'd :date9. x :${width}.'))
        self.assertEqual(run_plan(plan(producer(['. '+'X'*64],columns='d :date9. x :$64.')))['datasets']['extra']['rows'][0]['x'],'X'*64)
        self.refuse(producer(['. '+'X'*79],columns='d :date9. x :$64.'))
        many=''.join(producer([],name='d'+str(i)) for i in range(8));plan(many)
        self.refuse(many+producer([],name='excess'))
        formats=producer([])+''.join("proc format;value usr_f"+chr(97+i)+" low-high='X';run;" for i in range(8))
        plan(formats);self.refuse(formats+"proc format;value usr_excess low-high='X';run;")
        titles=producer([])+'title;\n'*32;plan(titles);self.refuse(titles+'title;')
        twice=SOURCE+'proc print data=dates;format born cohort.;run;';plan(twice)
        self.refuse(twice+'proc print data=dates;format born cohort.;run;')

    def test_range_count_bound(self):
        from sas_semantics import SAS_CALENDAR_MIN_DAY as minimum,SAS_CALENDAR_MAX_DAY as maximum
        value=plan();args=value['steps'][1]['operations'][0]['args']
        for count in (32,33):
            args['ranges']=[{'lower':minimum+i,'upper':minimum+i if i<count-1 else maximum,
                             'render':{'kind':'literal','text':'X'}} for i in range(count)]
            if count==32:run_plan(value)
            else:
                with self.assertRaises(ValueError):run_plan(value)

    def test_exact_portable_shapes_and_types_even_empty_tables(self):
        original=plan(producer([]));mutations=[]
        for key,value in [('version',True),('version',1),('tickets',[{}]),('steps',()),('matched',{})]:
            altered=deepcopy(original);altered[key]=value;mutations.append(altered)
        for key,value in [('kind','data'),('line',True),('inputs',['x']),('by',['d']),('where',{}),('nodupkey',0),('extra',1)]:
            altered=deepcopy(original);altered['steps'][0][key]=value;mutations.append(altered)
        for key,value in [('records',[None]),('records',()),('source_lines',[1]*6),('columns',[]),('extra',1)]:
            altered=deepcopy(original);altered['steps'][0]['operations'][0]['args'][key]=value;mutations.append(altered)
        for key,value in [('length',True),('length',9),('read','integer'),('name','_n_'),('extra',1)]:
            altered=deepcopy(original);altered['steps'][0]['operations'][0]['args']['columns'][0][key]=value;mutations.append(altered)
        for value in mutations:
            with self.subTest(value=value),self.assertRaises((ValueError,RuntimeError)):run_plan(value)

    def test_invalid_portable_render_even_unused_refuses(self):
        for key,value in [('width',50),('width',True),('width','37'),('name','date'),('extra',1)]:
            altered=plan();altered['steps'][1]['operations'][0]['args']['ranges'][0]['render'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):run_plan(altered)

    def test_hidden_markers_and_cycles_refuse(self):
        old=compile_plan('data _null_;x=1;run;').to_dict()
        old['steps'][0]['operations'][0]['args']['hidden']={'kind':'date_data'}
        with self.assertRaises(ValueError):run_plan(old)
        value=plan();value['matched'].append({'kind':'date_data'})
        with self.assertRaises(ValueError):run_plan(value)
        value=plan();value['matched'].append(value)
        with self.assertRaises(ValueError):run_plan(value)

    def test_nonempty_initial_catalog_and_partial_execution_refuse(self):
        with self.assertRaises(ValueError):run_plan(plan(),{'external':{'rows':[],'schema':{}}})
        value=plan();value['tickets']=[{'reason':'test'}]
        with self.assertRaises(ValueError):run_plan(value,allow_partial=True)

    def test_symbolic_date_endpoints_keep_their_roles(self):
        text=SOURCE.replace("'01JAN2000'd-high='New era'", "'01JAN2000'd-'30DEC3999'd='New era' high-high='Last'")
        self.refuse(text)
        data=SOURCE.split('proc format;',1)[0]
        self.refuse(data+"proc format;value cohort low-low='First' '02JAN1753'd-high='Rest';run;")

    def test_cpp_stays_blocked(self):
        self.assertTrue(cpp_translate(SOURCE).blocked)

    def test_format_and_title_state_are_per_job(self):
        run_plan(plan());value=SOURCE.replace('title \'Dates\';','')
        self.assertFalse(run_plan(plan(value))['reports']['print_01.txt'].startswith('TITLE:'))
        self.refuse(SOURCE.split('proc format;',1)[0]+'proc print data=dates;format born cohort.;run;')

    def test_preflight_does_not_render_but_late_execution_fails(self):
        value=plan(late_failure())
        with patch.object(dates,'_formatted',side_effect=AssertionError('render during preflight')):
            dates.validate_program(value)
        with self.assertRaisesRegex(ValueError,'row'):run_plan(value)
        job=build_job(late_failure());self.assertEqual(job.code,1);self.assertIsNone(job.result)

    def test_late_cli_failure_does_not_publish_an_earlier_report(self):
        with tempfile.TemporaryDirectory(prefix='saschi-date-atomic-') as temporary:
            directory=Path(temporary);path=directory/'source.sas';path.write_text(late_failure())
            run=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(directory/'job')],
                               capture_output=True,text=True,cwd=ROOT,timeout=120)
            self.assertEqual(run.returncode,1,run.stderr)
            receipt=json.loads((directory/'job'/'receipt.json').read_text())
            self.assertFalse(receipt['accepted']);self.assertNotIn('reports',receipt)
            self.assertFalse((directory/'job'/'reports').exists());self.assertFalse((directory/'job'/'result.json').exists())
            self.assertFalse((directory/'job'/'observed.json').exists())
            self.assertFalse(any(p.name.startswith('.saschi-') for p in directory.iterdir()))

    def test_preexisting_rules_and_capabilities_preserved(self):
        rulebook=json.loads((ROOT/'docs/sasconversionrulebook.json').read_text())
        canonical=json.dumps(rulebook['rules'][:123],sort_keys=True,separators=(',',':')).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),'aba7eac292eb77ddc9dcee1e0423f474d6f09bd0f81f25f202b2907336c744dc')
        original_keys=['note', 'plan_version', 'evidence', 'comparison', 'data_events', 'typed_metadata', 'cpp', 'counted_do', 'length_reverse', 'substr', 'substr_compositions', 'do_if', 'bitwise', 'lag_execution', 'calendar', 'sum_statement', 'do_until', 'division', 'int', 'do_while', 'numeric_arrays', 'do_over', 'counted_nested', 'put_mixed_numeric', 'trim_strip', 'input_list', 'multiplication', 'put_numeric_discovery', 'projection', 'projection_options', 'binary64', 'elementary_functions', 'fractional_put', 'numeric_projection', 'numeric_set', 'sql_create', 'pipeline_input', 'pipeline_arrays', 'pipeline_loops', 'numeric_pipeline', 'inline_csv', 'input_ranges', 'grouped_do', 'loop_transfer', 'numeric_ranges', 'csv_export', 'scalar_jump', 'scalar_link', 'numeric_sqrt', 'numeric_log', 'rounded_sum', 'proc_means', 'proc_print', 'character_input', 'mixed_print', 'logical_title', 'bitwise_output', 'numeric_invalue', 'formatted_input', 'labelled_print', 'default_means', 'informat_title', 'directed_sort', 'descriptor_sort_all', 'sort_input_keep', 'sort_duplicates', 'sort_replacement', 'sort_duplicate_reports', 'sort_input_drop', 'sort_directed_projection']
        capabilities={k:rulebook['runtime_capabilities'][k] for k in original_keys}
        self.assertEqual(hashlib.sha256(json.dumps(capabilities,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'672a39c476c5c4b2f14455f657aac1bef4e8b8efd341fe8d01b51c5f67f49482')


if __name__=='__main__':unittest.main()
