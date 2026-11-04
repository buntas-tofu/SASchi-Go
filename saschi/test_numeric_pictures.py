"""Strict source/portable and actual-publication controls for numeric PICTURE."""
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
from .job import build_job
from .catalog import record_pass
from . import numeric_pictures as pictures,format_report as reports

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/numeric_pictures.sas').read_text()
EXPECTED=json.loads((ROOT/'examples/numeric_pictures_expected.json').read_text())


def plan(text=SOURCE):
    parsed=compile_plan(text)
    if parsed.blocked:raise AssertionError(parsed.tickets)
    return parsed.to_dict()


def records(values):
    before,rest=SOURCE.split('\ndatalines;\n',1);_,after=rest.split('\n;\n',1)
    return before+'\ndatalines;\n'+('\n'.join(values)+'\n' if values else '')+';\n'+after


def late_failure():
    text=SOURCE+"proc format;picture usr_long low-high='"+'X'*40+"';run;\n"
    text+='proc report data=flights nowd;columns '+' '.join('delay=c'+str(i) for i in range(11))+';'
    text+=''.join('define c'+str(i)+' / display format=usr_long.;' for i in range(11))
    return text+'run;'


class NumericPictureTests(unittest.TestCase):
    def refuse(self,text):self.assertTrue(compile_plan(text).blocked,text)

    def test_original_complete_result_and_bom_same_data_distinct_frame(self):
        self.assertEqual(run_plan(plan()),EXPECTED);self.assertEqual(run_plan(plan('\ufeff'+SOURCE)),EXPECTED)
        a=[];pictures.run_program(plan(),trace=a);b=[];pictures.run_program(plan('\ufeff'+SOURCE),trace=b)
        self.assertEqual(a[1:],b[1:]);self.assertNotEqual(a[0],b[0]);self.assertIn('"02 minutes"',EXPECTED['reports']['report_01.txt'])

    def test_source_frame_accounting_and_raw_hash(self):
        for prefix,size in [('',0),('\ufeff',3)]:
            text=prefix+SOURCE;cat,c=record_pass(text,compile_plan(text))
            with cat:
                self.assertEqual((c.n_statements,c.n_routed,c.n_unrouted,c.n_functions),(19,18,1,0))
                self.assertEqual(cat.completeness().as_record(),c.as_record())
                if size:self.assertEqual(c.as_record()['source_prefix'],{'policy':'numeric-picture-envelope-v1','bytes':3,'encoding':'utf8-bom'})
                else:self.assertNotIn('source_prefix',c.as_record())
            job=build_job(text);self.assertEqual(job.receipt['source_sha256'],hashlib.sha256(text.encode()).hexdigest())

    def test_date_picture_obs_is_a_dataset_option(self):
        text=(ROOT/'examples/picture_dates.sas').read_text();cat,c=record_pass(text,compile_plan(text))
        with cat:self.assertEqual(c.n_functions,0)

    def test_prefix_refusals_do_not_broaden_other_families(self):
        for text in ['\ufeff\ufeff'+SOURCE,SOURCE+'\ufeff',SOURCE.replace('Early','Éarly'),'\ufeffdata _null_;x=1;run;',
                     '\ufeff'+(ROOT/'examples/picture_dates.sas').read_text()]:self.refuse(text)
        self.assertEqual(pictures.accounting_frame('\ufeffdata _null_;x=1;run;'),('\ufeffdata _null_;x=1;run;',0))

    def test_input_exact_width_separator_signed_and_empty(self):
        for row in ['1 AB','1 ABCD','1  ABC','1\tABC','1.5 ABC','. ABC','2147483648 ABC','1 A1C','1 ABC X']:
            with self.subTest(row=row):self.refuse(records([row]))
        result=run_plan(plan(records(['-2147483647 ABC']).replace('format=comma12.','')))
        self.assertEqual(result['datasets']['flights']['rows'][0]['delay'],-2147483647.)
        self.assertEqual(run_plan(plan(records([])))['datasets']['flights']['schema'],EXPECTED['datasets']['flights']['schema'])
        self.refuse(records(['1 ABC']*1001))

    def test_range_roles_gaps_overlaps_and_fractions(self):
        for old,new in [('low-<0','low<-<0'),('low-<0','high-<0'),('10<-high','10<-<high'),('10<-high','11<-high'),
                        ('1<-10','1-10'),('1<-10','1.5-10'),("0='On time'","other='On time'")]:self.refuse(SOURCE.replace(old,new))

    def test_templates_limit_and_unused_invalid_definition(self):
        for replacement in ["'More than 10'", "'00 late'", "'"+'9'*17+"'", "'99.9'", "'&macro'", "'"+'X'*41+"'"]:
            self.refuse(SOURCE.replace("'09 late'",replacement))
        self.refuse(SOURCE+"proc format;picture usr_unused low-high='Invalid 10';run;")
        value=run_plan(plan(SOURCE.replace("'09 late'","' Message 10' (noedit)")))
        self.assertIn('" Message 10"',value['reports']['report_01.txt'])

    def test_noedit_and_digit_selector_variants(self):
        for replacement in ["'09 late'", "'99 late'", "'999 late'", "' More than 10' (noedit)"]:
            result=run_plan(plan(SOURCE.replace("'09 late'",replacement)))
            self.assertEqual(result['datasets'],EXPECTED['datasets'])
        result=run_plan(plan(records(['100 ABC','101 DEF','-2 GHI'])))
        self.assertIn('"0 late"',result['reports']['report_01.txt']);self.assertIn('"1 late"',result['reports']['report_01.txt'])

    def test_formats_aliases_namespace_and_eager_empty_types(self):
        for old,new in [('usr_nine','arbitrary'),('delay=two','absent=two'),('delay=two','delay=delay'),('format=comma12.','format=dollar12.'),
                        ('format=usr_edited.','format=date9.'),('display format=','format='),
                        ('input delay destination $3.','input delay delay $3.'),('define plain','define absent')]:self.refuse(SOURCE.replace(old,new))
        self.refuse(records([]).replace('column delay','column destination').replace('define delay','define destination'))
        self.refuse(SOURCE+"proc format;picture usr_nine low-high='Same';run;")

    def test_preflight_never_renders_or_formats(self):
        with patch.object(pictures,'field',side_effect=AssertionError('preflight formatting')),patch.object(reports,'render',side_effect=AssertionError('preflight render')):pictures.validate_program(plan())

    def test_portable_exact_shapes_and_prefix_consistency(self):
        mutations=[]
        for key,value in [('version',True),('tickets',[{}]),('steps',()),('extra',1)]:
            p=plan();p[key]=value;mutations.append(p)
        for key,value in [('line',True),('inputs',['bad']),('by',['x']),('extra',1)]:
            p=plan();p['steps'][0][key]=value;mutations.append(p)
        for key,value in [('width',True),('records',()),('source_prefix',False),('extra',1)]:
            p=plan();p['steps'][0]['operations'][0]['args'][key]=value;mutations.append(p)
        p=plan();p['steps'][1]['operations'][0]['args']['source_prefix']='utf8-bom';mutations.append(p)
        for key,value in [('lower',True),('upper',1.),('noedit',1),('extra',1)]:
            p=plan();p['steps'][1]['operations'][0]['args']['ranges'][0][key]=value;mutations.append(p)
        for value in mutations:
            with self.subTest(value=value),self.assertRaises((ValueError,RuntimeError)):run_plan(value)

    def test_hidden_markers_cycles_partial_catalog_and_foreign_source(self):
        p=compile_plan('data _null_;x=1;run;').to_dict();p['hidden']={'kind':'number_picture'}
        with self.assertRaises(ValueError):run_plan(p)
        p=plan();p['matched'].append(p)
        with self.assertRaises(ValueError):run_plan(p)
        with self.assertRaises(ValueError):run_plan(plan(),{'external':{}})
        p=plan();p['tickets']=[{}]
        with self.assertRaises(ValueError):run_plan(p,allow_partial=True)
        self.refuse(SOURCE+'proc print data=flights;run;')

    def test_job_local_titles_and_composition_bounds(self):
        run_plan(plan());result=run_plan(plan(SOURCE.replace("title 'Integer pictures';",'')))
        self.assertFalse(result['reports']['report_01.txt'].startswith('TITLE:'))
        second='proc report data=flights nowd;columns delay;define delay / display format=comma12.;run;'
        plan(SOURCE+second);self.refuse(SOURCE+second+second)
        plan(SOURCE+'title;'*31);self.refuse(SOURCE+'title;'*32)

    def test_late_real_renderer_failure_no_partial_publication(self):
        value=plan(late_failure());seen=[];original=reports.validate_reports
        def observe(artifacts):result=original(artifacts);seen.append(len(artifacts));return result
        with patch.object(reports,'validate_reports',observe):job=build_job(late_failure())
        self.assertEqual(seen,[1]);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        with tempfile.TemporaryDirectory(prefix='saschi-number-atomic-') as temporary:
            area=Path(temporary);path=area/'source.sas';path.write_text(late_failure())
            run=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(area/'job')],capture_output=True,text=True,cwd=ROOT,timeout=120)
            self.assertEqual(run.returncode,1,run.stderr);self.assertFalse(json.loads((area/'job/receipt.json').read_text())['accepted'])
            for name in ('reports','exports','result.json','observed.json'):self.assertFalse((area/'job'/name).exists())


if __name__=='__main__':unittest.main()
