"""Source, portable and actual execution boundaries for numeric GROUPFORMAT."""
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
from . import groupformat as groups
from . import format_report as reports

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/groupformat.sas').read_text()
EXPECTED=json.loads((ROOT/'examples/groupformat_expected.json').read_text())


def plan(text=SOURCE):
    parsed=compile_plan(text)
    if parsed.blocked:raise AssertionError(parsed.tickets)
    return parsed.to_dict()


def source(records):
    before,rest=SOURCE.split('\ncards;\n',1);_,after=rest.split('\n;\n',1)
    return before+'\ncards;\n'+('\n'.join(records)+'\n' if records else '')+';\n'+after


def late_failure():
    text=SOURCE+"proc format;value usr_long low-high='"+'X'*128+"';run;\n"
    text+='proc report data=ends nowd;columns salary=a salary=b salary=c salary=d;'
    for alias in 'abcd':text+='define '+alias+' / display format=usr_long.;'
    return text+'run;'


class GroupFormatTests(unittest.TestCase):
    def refuse(self,text):self.assertTrue(compile_plan(text).blocked,text)

    def test_original_whole_values_schema_reports_and_dual_output(self):
        actual=run_plan(plan());self.assertEqual(actual,EXPECTED)
        self.assertEqual([row['id'] for row in actual['datasets']['ends']['rows']],[1.,3.,4.,5.,6.,6.])
        self.assertEqual(actual['datasets']['wages']['rows'],EXPECTED['datasets']['wages']['rows'])
        self.assertEqual(list(actual['datasets']['ends']['schema']),['id','salary','hired'])

    def test_adjacent_equal_formatted_labels_merge_raw_ranges(self):
        result=run_plan(plan(SOURCE.replace("10-<20='Mid'","10-<20='Low'")))
        self.assertEqual([r['id'] for r in result['datasets']['ends']['rows']],[1.,5.,6.,6.])

    def test_nonadjacent_equal_labels_are_separate_runs(self):
        result=run_plan(plan(SOURCE.replace("20-high='High'","20-high='Low'")))
        self.assertEqual([r['id'] for r in result['datasets']['ends']['rows']],[1.,3.,4.,5.,6.,6.])

    def test_tied_values_keep_distinct_row_identity(self):
        value=run_plan(plan(source(['1 4 01JAN1960','2 4 02JAN1960','3 4 03JAN1960'])))
        self.assertEqual([r['id'] for r in value['datasets']['ends']['rows']],[1.,3.])
        self.assertEqual([r['id'] for r in value['datasets']['wages']['rows']],[1.,2.,3.])

    def test_one_observation_emits_twice_and_empty_preserves_schema(self):
        value=run_plan(plan(source(['1 10 01JAN1960'])))
        self.assertEqual([r['id'] for r in value['datasets']['ends']['rows']],[1.,1.])
        value=run_plan(plan(source([])));self.assertEqual(value['datasets']['ends']['rows'],[])
        self.assertEqual(value['datasets']['ends']['schema'],EXPECTED['datasets']['ends']['schema'])
        self.assertEqual(len(value['reports']['report_01.txt'].splitlines()),2)

    def test_grouping_requires_raw_sort_nonmissing_nondate_and_bounded_count(self):
        for records in [['1 10 01JAN1960','2 9 01JAN1960'],['1 . 01JAN1960'],['1 4 01JAN1960']*501]:
            with self.subTest(records=len(records)):self.refuse(source(records))
        self.assertEqual(len(run_plan(plan(source(['1 4 01JAN1960']*500)))['datasets']['ends']['rows']),2)
        self.refuse(source(['1 01JAN1960 01JAN1960']).replace('id salary hired :date9.','id salary :date9. hired :date9.'))

    def test_group_source_forms_are_exact_and_no_chaining(self):
        for old,new in [('by groupformat salary','by salary'),('by groupformat salary','by groupformat descending salary'),
                        ('by groupformat salary','by groupformat salary id'),('by groupformat salary','by groupformat salary notsorted'),
                        ('format salary usr_band.','format id usr_band.'),('set wages','set absent'),('data ends','data wages'),
                        ('if last.salary then output','else if last.salary then output'),('if first.salary then output','if first.id then output'),
                        ('if last.salary then output','if last.salary then output other')]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE+'data next;set ends;by groupformat salary;format salary usr_band.;if first.salary then output;if last.salary then output;run;')

    def test_numeric_value_ranges_names_types_and_unused_definitions_refuse(self):
        for old,new in [("low-<10","low-10"),("10-<20","11-<20"),("20-high","19-high"),('usr_band','arbitrary'),
                        ("low-<10","low-<10.5"),("'Low'","''"),("'Low'","' Low'"),("'Low'","'&name'"),
                        ("'High'","'"+'X'*129+"'")]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE+"proc format;value usr_unused low-1='A';run;")
        self.refuse(SOURCE+"proc format;value usr_band low-high='X';run;")

    def test_report_aliases_formats_and_labels(self):
        result=run_plan(plan(SOURCE.replace("'Pay band'","'Pay ''band'''")))
        self.assertIn('"Pay \'band\'"',result['reports']['report_01.txt'])
        for old,new in [('salary=band','salary=salary'),('salary=band','absent=band'),('define band','define absent'),
                        ('format=dollar12.','format=comma12.'),('format=dollar12.','format=date9.'),
                        ('format=date9.','format=unavailable.'),('format=usr_band.','format=worddate20.'),
                        ('display format=dollar12.','format=dollar12.'),('format=dollar12.',''),
                        ('nowd;','nowd missing;'),('columns id salary','columns id salary,*'),
                        ("'Pay band'","'&caption'")]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))

    def test_open_high_cannot_be_reinterpreted_as_finite_domain_edge(self):
        self.refuse(SOURCE.replace("20-high='High'","20-<high='High' 2147483647-high='Last'"))

    def test_currency_domain_and_date_missing(self):
        self.refuse(source(['1 -1 01JAN1960']))
        self.refuse(source(['1 1000000000 01JAN1960']))
        result=run_plan(plan(source(['1 999999999 .'])))
        self.assertIn('"$999,999,999"',result['reports']['report_01.txt'])
        self.assertIn('"."',result['reports']['report_01.txt'])

    def test_public_descriptors_do_not_fabricate_persistent_formats(self):
        result=run_plan(plan())
        self.assertEqual(result['datasets']['ends']['schema']['salary'],{'type':'number','length':8})
        self.refuse(SOURCE.replace('define band / format=usr_band. \'Pay band\';',''))

    def test_preflight_does_not_group_or_render(self):
        value=plan()
        with (patch.object(groups,'execute_groups',side_effect=AssertionError('grouping during validation')),
              patch.object(reports,'render',side_effect=AssertionError('rendering during validation'))):
            groups.validate_program(value)

    def test_actual_grouping_executes_once(self):
        value=plan();original=groups.execute_groups;seen=[]
        def observe(*args,**kwargs):seen.append(1);return original(*args,**kwargs)
        with patch.object(groups,'execute_groups',observe):result=run_plan(value)
        self.assertEqual(seen,[1]);self.assertEqual(result,EXPECTED)

    def test_portable_exact_types_fields_and_defaults(self):
        mutations=[]
        for key,value in [('version',True),('version',1),('tickets',[{}]),('matched',[{}]),('steps',()),('extra',1)]:
            item=plan();item[key]=value;mutations.append(item)
        for key,value in [('line',True),('inputs',[]),('kind','data'),('by',['salary']),('where',{}),('extra',1)]:
            item=plan();item['steps'][2][key]=value;mutations.append(item)
        for key,value in [('source',[]),('key','hired'),('format',{}),('source_lines',[1]*7),('extra',1)]:
            item=plan();item['steps'][2]['operations'][0]['args'][key]=value;mutations.append(item)
        for key,value in [('lower',True),('upper',1.),('text',''),('extra',1)]:
            item=plan();item['steps'][1]['operations'][0]['args']['ranges'][0][key]=value;mutations.append(item)
        for key,value in [('display',1),('format',False),('label',{}),('extra',1)]:
            item=plan();item['steps'][3]['operations'][0]['args']['definitions']['salary'][key]=value;mutations.append(item)
        for item in mutations:
            with self.subTest(item=item),self.assertRaises((ValueError,RuntimeError)):run_plan(item)

    def test_hidden_markers_cycles_catalog_partial_and_foreign_families_refuse(self):
        old=compile_plan('data _null_;x=1;run;').to_dict();old['steps'][0]['operations'][0]['args']['hidden']={'kind':'numeric_value'}
        with self.assertRaises(ValueError):run_plan(old)
        value=plan();value['matched'].append(value)
        with self.assertRaises(ValueError):run_plan(value)
        with self.assertRaises(ValueError):run_plan(plan(),{'external':{}})
        value=plan();value['tickets']=[{'reason':'test'}]
        with self.assertRaises(ValueError):run_plan(value,allow_partial=True)
        self.refuse(SOURCE+'proc print data=ends;format hired date9.;run;')
        self.refuse(SOURCE+"proc format;picture usr_date low-high='%Y' (datatype=date);run;")

    def test_job_local_title_format_state_and_bounds(self):
        run_plan(plan());text=SOURCE.replace("title 'Group endpoints';",'')
        self.assertFalse(run_plan(plan(text))['reports']['report_01.txt'].startswith('TITLE:'))
        self.refuse(SOURCE.replace('value usr_band','value salgrp').replace('usr_band.;','missing.;'))
        text=SOURCE+'title;\n'*30;plan(text);self.refuse(text+'title;')
        second='proc report data=ends nowd;columns salary;define salary / display format=dollar12.;run;'
        plan(SOURCE+second);self.refuse(SOURCE+second+second)

    def test_late_real_renderer_failure_has_no_partial_publication(self):
        value=plan(late_failure());seen=[];original=reports.validate_reports
        def observe(artifacts):result=original(artifacts);seen.append(len(artifacts));return result
        with patch.object(reports,'validate_reports',observe):job=build_job(late_failure())
        self.assertEqual(seen,[1]);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        with tempfile.TemporaryDirectory(prefix='saschi-group-atomic-') as temporary:
            area=Path(temporary);path=area/'source.sas';path.write_text(late_failure())
            run=subprocess.run([sys.executable,'-m','saschi','run',str(path),'--output',str(area/'job')],capture_output=True,text=True,cwd=ROOT,timeout=120)
            self.assertEqual(run.returncode,1,run.stderr)
            self.assertFalse(json.loads((area/'job'/'receipt.json').read_text())['accepted'])
            for name in ('reports','exports','result.json','observed.json'):self.assertFalse((area/'job'/name).exists())


if __name__=='__main__':unittest.main()
