"""Strict admission, state and actual late failure for week callback composition."""
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
from . import week_callbacks as week,format_report as reports

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/week_callbacks.sas').read_text()
EXPECTED=json.loads((ROOT/'examples/week_callbacks_expected.json').read_text())


def plan(text=SOURCE):
    p=compile_plan(text)
    if p.blocked:raise AssertionError(p.tickets)
    return p.to_dict()


def source(rows):
    before,rest=SOURCE.split('\n cards;\n',1);_,after=rest.split('\n;\n',1)
    return before+'\n cards;\n'+('\n'.join(rows)+'\n' if rows else '')+';\n'+after


def late_failure():
    text=SOURCE+'proc report data=deliveries nowd;columns customer (\''+'S'*128+"' "+' '.join('shipped=c'+str(i) for i in range(5))+');define customer / order;'
    text+=''.join('define c'+str(i)+" / display format=usr_begin12. '"+'L'*128+"';" for i in range(5))
    return text+'run;'


class WeekCallbackTests(unittest.TestCase):
    def refuse(self,text):self.assertTrue(compile_plan(text).blocked,text)

    def test_whole_result_preserves_rows_and_suppresses_repeated_order_only(self):
        result=run_plan(plan());self.assertEqual(result,EXPECTED)
        self.assertEqual(len(result['datasets']['deliveries']['rows']),9)
        lines=result['reports']['report_01.txt'].splitlines();self.assertTrue(lines[3].startswith('"" "102"'));self.assertIn('"Window/First"',lines[1])

    def test_saturday_sunday_epoch_and_leap_literal_dates(self):
        rows=run_plan(plan())['reports']['report_01.txt'];self.assertIn('"28DEC1959" "08JAN1960"',rows);self.assertIn('"28FEB2000" "03MAR2000"',rows);self.assertIn('"25DEC2023" "05JAN2024"',rows)

    def test_empty_and_missing_keep_descriptor_and_period_fields(self):
        result=run_plan(plan(source([])));self.assertEqual(result['datasets']['deliveries']['schema'],EXPECTED['datasets']['deliveries']['schema']);self.assertEqual(result['datasets']['deliveries']['rows'],[])
        result=run_plan(plan(source(['10 . 1'])));self.assertIn('"." "." "."',result['reports']['report_01.txt'])

    def test_function_body_signature_names_and_unused_definitions_are_strict(self):
        for old,new in [('week.2','week.1'),("'week.2',d,0","'week.2',d,1"),("'week.7',d,1)-1","'week.7',d,1)"),('$9;','$10;'),
                        ('usr_monday(d)','arbitrary(d)'),('return(put(x,date9.))','return(put(d,date9.))'),('x=intnx','d=intnx'),('endsub;','end;'),('outlib=work.functions.Calendar','outlib=other.functions.Calendar'),('quit;','run;')]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE.replace('quit;',"function usr_bad(d) $9;x=unknown(d);return(put(x,date9.));endsub;quit;"))

    def test_cmplib_and_format_dependencies_namespace_are_job_local(self):
        for old,new in [('options cmplib=work.functions;',''),('options cmplib=work.functions','options cmplib=work.other'),('other=[usr_monday()]','other=[absent()]'),
                        ('other=[usr_monday()]','low-high=[usr_monday()]'),('other=[usr_monday()]','other=[usr_monday(1)]'),('value usr_begin','value arbitrary'),('usr_begin12.','usr_begin9.'),('usr_begin12.','usr_missing12.')]:self.refuse(SOURCE.replace(old,new))
        self.refuse('options cmplib=work.functions;'+SOURCE)
        self.refuse(SOURCE+"proc format;value usr_begin other=[usr_monday()];run;")
        run_plan(plan());self.refuse(SOURCE[SOURCE.index('options cmplib='):])

    def test_callback_date_type_and_calendar_output_bounds_validate_eagerly(self):
        self.refuse(SOURCE.replace('shipped=beginning','orderid=beginning'))
        plan(source(['10 01JAN1753 1','11 31DEC3999 2']))
        self.refuse(source(['10 31DEC1752 1']))
        self.refuse(source(['10 01JAN4000 1']))
        self.refuse(source([]).replace('shipped=ending','orderid=ending'))

    def test_order_requires_two_digit_nonmissing_ascending_first_numeric_column(self):
        for rows in [['10 01JAN1960 1','09 01JAN1960 2'],['1 01JAN1960 1'],['100 01JAN1960 1'],['. 01JAN1960 1']]:self.refuse(source(rows))
        for old,new in [('columns customer orderid','columns orderid customer'),("order 'Customer'","order display 'Customer'"),("order 'Customer'","order format=10. 'Customer'"),("order 'Customer'","display 'Customer'")]:self.refuse(SOURCE.replace(old,new))

    def test_report_span_aliases_formats_and_all_defines(self):
        for old,new in [("('Window' shipped=beginning shipped=ending)",'shipped=beginning shipped=ending'),('shipped=ending','shipped=beginning'),('shipped=ending','absent=ending'),
                        ('format=10.','format=9.'),('format=weekdate.','format=date9.'),('define orderid','define absent'),("title 'Week callbacks';",'compute x;endcomp;')]:self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE.replace("define orderid / format=10. 'Order';",''))

    def test_preflight_does_not_execute_callback_or_renderer(self):
        with patch.object(week,'callback',side_effect=AssertionError('preflight callback')),patch.object(week,'render',side_effect=AssertionError('preflight render')):week.validate_program(plan())

    def test_actual_callback_once_per_displayed_cell_including_missing(self):
        seen=[];original=week.callback
        def observe(value,body):seen.append(value);return original(value,body)
        with patch.object(week,'callback',observe):result=run_plan(plan())
        self.assertEqual(result,EXPECTED);self.assertEqual(len(seen),18);self.assertEqual(seen.count(None),2)

    def test_portable_exact_fields_types_defaults_and_eager_unused_function(self):
        changes=[]
        for key,value in [('version',True),('tickets',[{}]),('extra',1)]:p=plan();p[key]=value;changes.append(p)
        for key,value in [('inputs',['functions']),('line',True),('extra',1)]:p=plan();p['steps'][0][key]=value;changes.append(p)
        for key,value in [('offset',True),('return_width',9.),('anchor',1),('local','d'),('extra',1)]:p=plan();p['steps'][0]['operations'][0]['args']['functions'][0][key]=value;changes.append(p)
        for key,value in [('library',[]),('extra',1)]:p=plan();p['steps'][1]['operations'][0]['args'][key]=value;changes.append(p)
        p=plan();p['steps'][2]['operations'][0]['args']['function']=[];changes.append(p)
        for key,value in [('order',1),('display',1),('format',False),('extra',1)]:p=plan();p['steps'][5]['operations'][0]['args']['definitions']['shipped'][key]=value;changes.append(p)
        for p in changes:
            with self.subTest(p=p),self.assertRaises((ValueError,RuntimeError)):run_plan(p)

    def test_cycles_hidden_markers_partial_catalog_foreign_source_refuse(self):
        p=compile_plan('data _null_;x=1;run;').to_dict();p['hidden']={'kind':'week_library'}
        with self.assertRaises(ValueError):run_plan(p)
        p=plan();p['matched'].append(p)
        with self.assertRaises(ValueError):run_plan(p)
        with self.assertRaises(ValueError):run_plan(plan(),{'external':{}})
        p=plan();p['tickets']=[{}]
        with self.assertRaises(ValueError):run_plan(p,allow_partial=True)
        self.refuse('\ufeff'+SOURCE);self.refuse(SOURCE+'proc print data=deliveries;run;')

    def test_title_state_and_bounds(self):
        run_plan(plan());self.assertFalse(run_plan(plan(SOURCE.replace("title 'Week callbacks';",'')))['reports']['report_01.txt'].startswith('TITLE:'))
        plan(SOURCE+'title;'*30);self.refuse(SOURCE+'title;'*31)
        report=SOURCE[SOURCE.index('proc report '):SOURCE.rindex('title;')];plan(SOURCE+report);self.refuse(SOURCE+report+report)

    def test_real_second_header_overflow_publishes_no_partial_result(self):
        plan(late_failure());seen=[];original=reports.validate_reports
        def observe(artifacts):result=original(artifacts);seen.append(len(artifacts));return result
        with patch.object(reports,'validate_reports',observe):job=build_job(late_failure())
        self.assertEqual(seen,[1]);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        with tempfile.TemporaryDirectory(prefix='saschi-week-atomic-') as temporary:
            area=Path(temporary);p=area/'source.sas';p.write_text(late_failure());run=subprocess.run([sys.executable,'-m','saschi','run',str(p),'--output',str(area/'job')],capture_output=True,text=True,cwd=ROOT,timeout=120)
            self.assertEqual(run.returncode,1,run.stderr);self.assertFalse(json.loads((area/'job/receipt.json').read_text())['accepted'])
            for name in ('reports','exports','result.json','observed.json'):self.assertFalse((area/'job'/name).exists())


if __name__=='__main__':unittest.main()
