"""Strict source/portable/actual execution controls for the postal composition."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from .plan import compile_plan
from .runtime import run_plan
from .job import build_job
from . import postal_function as postal,postal_reference as reference

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/postal_function.sas').read_text()


def plan(text=SOURCE):
    p=compile_plan(text)
    if p.blocked:raise AssertionError(p.tickets)
    return p.to_dict()


def source(records):
    before,rest=SOURCE.split('\n cards;\n',1);_,after=rest.split('\n;\n',1)
    return before+'\n cards;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+after


def late_failure():
    text=SOURCE[:SOURCE.index('data contacts;')]
    names=['country','postal']+list('abcdef');text+='data contacts;infile cards dlm=\',\' dsd;input country :$2. postal :$5. '+' '.join(c+':$33.' for c in 'abcdef')+';cards;\n'
    text+=','.join(['ZZ','00000']+['\\'*33]*6)+'\n;\nrun;proc sort data=contacts;by country;run;'
    def report(cols):return 'proc report data=contacts nowd;columns '+cols+";by country;define region / computed 'Region';compute region / char length=5;region=usr_region_of(country,postal);endcomp;run;"
    return text+report('country postal region')+report(' '.join(names)+' region')


class PostalFunctionTests(unittest.TestCase):
    def refuse(self,text):self.assertTrue(compile_plan(text).blocked,text)

    def test_complete_schema_stable_sort_leading_zero_and_computed_not_stored(self):
        result=run_plan(plan());table=result['datasets']['contacts'];self.assertEqual([r['id'].rstrip() for r in table['rows']],['4','6','1','5','3','2'])
        self.assertNotIn('region',table['schema']);self.assertEqual(table['schema']['postal'],{'type':'character','length':5})
        self.assertIn('01040',[r['postal'] for r in table['rows']]);self.assertIn('0200 ',[r['postal'] for r in table['rows']]);self.assertTrue('"Kai \\"K\\" North"' in result['reports']['report_01.txt'],'escaped display value differs')

    def test_empty_preserves_schema_and_has_no_by_or_callback_rows(self):
        result=run_plan(plan(source([])));self.assertEqual(result['datasets']['contacts']['rows'],[]);self.assertEqual(len(result['reports']['report_01.txt'].splitlines()),2)

    def test_reference_receipt_is_explicit_only_for_this_family(self):
        job=build_job(SOURCE);self.assertEqual(job.code,0);self.assertEqual(job.receipt['postal_reference'],reference.metadata())
        self.assertNotIn('postal_reference',build_job('data _null_;x=1;run;').receipt)

    def test_character_ranges_groups_types_overlap_and_unused_bad_ranges_refuse(self):
        for old,new in [("'0200'-'0299'","'0200'-'1299'"),("'0200'-'0299'","'200'-'299'"),("'0200'-'0299'","low-high"),("'ACT'","'TOOLONG'"),("'ACT'","'act'"),('$usr_region','$arbitrary')]:self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE.replace("'8000'-'8999'='VIC'","'8000'-'8999'='VIC' '1000'-'1100'='XX'"))

    def test_exact_case_sensitive_branch_literals_and_function_signature(self):
        for old,new in [("='AU'","='au'"),("='US'","='us'"),('$5;','$6;'),('country $,code $','country,code $'),('return(region)','return(code)'),('region=put(code','region=put(country'),('region=zipstate(code)','region=unknown(code)'),('else region=\' \'','else region=\'X\''),('outlib=work.functions.Regions','outlib=other.functions.Regions'),('usr_region_of(country','arbitrary(country')]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE.replace('options cmplib=work.functions;',''));self.refuse(SOURCE.replace('cmplib=work.functions','cmplib=other.functions'))

    def test_unknown_us_au_codes_numeric_shapes_refuse_unknown_country_skips_lookup(self):
        for code,country in [('00000','US'),('1040','US'),('59017','US'),('0300','AU'),('02000','AU'),('abcd','AU')]:self.refuse(source([f'1,Person,Place,{code},{country}']))
        value=plan(source(['1,Person,Place,00000,ZZ']))
        with patch.object(reference,'zip_state',side_effect=AssertionError('unknown-country lookup')):result=run_plan(value)
        self.assertIn('""',result['reports']['report_01.txt'])

    def test_csv_quoting_width_missing_and_record_bounds(self):
        for record in ['1,Person,Place,01040','1,Person,Place,01040,US,extra','1,,Place,01040,US','1,.,Place,01040,US','1, Person,Place,01040,US',
                       '1,"Person"junk,Place,01040,US','1,Per"son,Place,01040,US','1,"Person,Place,01040,US','1,'+'X'*31+',Place,01040,US','1,Person,Place,01040,US\t']:
            with self.subTest(record=record):self.refuse(source([record]))
        self.refuse(source(['1,Person,Place,01040,US']*1001))

    def test_sort_owned_country_and_report_evaluation_order(self):
        for old,new in [('proc sort data=contacts','proc sort data=absent'),('by country;\nrun;','by descending country;\nrun;'),('by country;\nrun;','by postal;\nrun;'),
                        ('columns country city postal region id person','columns region country city postal id person'),('by country;\n define','by postal;\n define'),('char length=5','char length=6'),
                        ('region=usr_region_of(country,postal)','region=usr_region_of(postal,country)'),('region=usr_region_of(country,postal)','region=missing(country,postal)'),('columns country city postal region id person','columns country city postal region id absent')]:self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE.replace('proc sort data=contacts;\n by country;\nrun;',''))

    def test_preflight_does_not_sort_call_or_render(self):
        value=plan()
        with patch.object(postal,'execute_sort',side_effect=AssertionError('preflight sort')),patch.object(postal,'callback',side_effect=AssertionError('preflight callback')),patch.object(postal,'render',side_effect=AssertionError('preflight render')),patch.object(reference,'zip_state',side_effect=AssertionError('preflight ZIPSTATE')):postal.validate_program(value)

    def test_actual_sort_and_callback_counts_once_per_row(self):
        value=plan();sorts=[];calls=[];zips=[];s=postal.execute_sort;f=postal.callback;z=reference.zip_state
        def sort(*args,**kwargs):sorts.append(1);return s(*args,**kwargs)
        def callback(*args,**kwargs):calls.append(1);return f(*args,**kwargs)
        def zip_state(*args,**kwargs):zips.append(1);return z(*args,**kwargs)
        with patch.object(postal,'execute_sort',sort),patch.object(postal,'callback',callback),patch.object(reference,'zip_state',zip_state):run_plan(value)
        self.assertEqual((len(sorts),len(calls),len(zips)),(1,6,2))

    def test_portable_fields_types_profiles_and_reference_injection_refuse(self):
        changes=[]
        for key,value in [('version',True),('extra',1),('tickets',[{}])]:p=plan();p[key]=value;changes.append(p)
        for key,value in [('line',True),('inputs',['contacts']),('extra',1)]:p=plan();p['steps'][0][key]=value;changes.append(p)
        for key,value in [('lower',200),('upper','99999'),('text','XXYY'),('extra',1)]:p=plan();p['steps'][0]['operations'][0]['args']['ranges'][0][key]=value;changes.append(p)
        for key,value in [('return_width',True),('country','code'),('format',[]),('extra',1)]:p=plan();p['steps'][1]['operations'][0]['args']['function'][key]=value;changes.append(p)
        p=plan();p['steps'][3]['operations'][0]['args']['columns'][0]['width']=True;changes.append(p)
        for key,value in [('columns',()),('reference',{}),('country','postal'),('label',False),('extra',1)]:p=plan();p['steps'][5]['operations'][0]['args'][key]=value;changes.append(p)
        for p in changes:
            with self.subTest(p=p),self.assertRaises((ValueError,RuntimeError)):run_plan(p)

    def test_hidden_markers_cycles_partial_catalog_and_foreign_literal(self):
        p=compile_plan('data _null_;x=1;run;').to_dict();p['hidden']={'kind':'postal_library'}
        with self.assertRaises(ValueError):run_plan(p)
        p=plan();p['matched'].append(p)
        with self.assertRaises(ValueError):run_plan(p)
        with self.assertRaises(ValueError):run_plan(plan(),{'external':{}})
        p=plan();p['tickets']=[{}]
        with self.assertRaises(ValueError):run_plan(p,allow_partial=True)
        self.refuse('\ufeff'+SOURCE);self.assertFalse(compile_plan("data _null_;put 'zipstate(';run;").blocked)

    def test_job_local_state_title_and_composition_bounds(self):
        run_plan(plan());self.assertFalse(run_plan(plan(SOURCE.replace("title 'Country regions';",'')))['reports']['report_01.txt'].startswith('TITLE:'))
        self.refuse(SOURCE[SOURCE.index('options cmplib='):]);plan(SOURCE+'title;'*30);self.refuse(SOURCE+'title;'*31)
        report=SOURCE[SOURCE.index('proc report '):SOURCE.rindex('title;')];plan(SOURCE+report);self.refuse(SOURCE+report+report)

    def test_actual_second_row_overflow_has_no_partial_publication(self):
        plan(late_failure());seen=[];original=postal.validate_reports
        def observe(artifacts):result=original(artifacts);seen.append(len(artifacts));return result
        with patch.object(postal,'validate_reports',observe):job=build_job(late_failure())
        self.assertEqual(seen,[1]);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        with tempfile.TemporaryDirectory(prefix='saschi-postal-atomic-') as temp:
            area=Path(temp);p=area/'source.sas';p.write_text(late_failure());run=subprocess.run([sys.executable,'-m','saschi','run',str(p),'--output',str(area/'job')],capture_output=True,text=True,cwd=ROOT,timeout=120)
            self.assertEqual(run.returncode,1,run.stderr);self.assertFalse(json.loads((area/'job/receipt.json').read_text())['accepted'])
            for name in ('reports','exports','result.json','observed.json'):self.assertFalse((area/'job'/name).exists())


if __name__=='__main__':unittest.main()
