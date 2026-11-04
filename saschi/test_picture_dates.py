"""Admission, state and failure controls for the separate date-picture family."""
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
from .emit_cpp import translate as cpp
from . import picture_dates as picture

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'examples/picture_dates.sas').read_text()
EXPECTED=json.loads((ROOT/'examples/picture_dates_expected.json').read_text())


def plan(source=SOURCE):
    value=compile_plan(source)
    if value.blocked:raise AssertionError(value.tickets)
    return value.to_dict()


def producer(records,columns='d :date9.',name='owned'):
    return f'data {name};\ninfile cards;\ninput {columns};\ncards;\n'+('\n'.join(records)+'\n' if records else '')+';\nrun;\n'


def late_failure():
    # A valid first report is followed by eleven40-character missing-date labels.
    text=SOURCE.split('proc format;\npicture usr_epoch',1)[0]
    text+=producer([' '.join(['.']*11)],' '.join(f'd{i} :date9.' for i in range(11)))
    text+="proc format;picture usr_long low-high='"+'X'*40+"' (datatype=date) other='"+'X'*40+"';run;\n"
    text+='proc print data=owned;var '+' '.join(f'd{i}' for i in range(11))+';format '+' '.join(f'd{i}' for i in range(11))+' usr_long.;run;'
    return text


class PictureDateTests(unittest.TestCase):
    def refuse(self,text):self.assertTrue(compile_plan(text).blocked,text)

    def test_complete_original_preserves_storage_and_both_snapshots(self):
        actual=run_plan(plan());self.assertEqual(actual,EXPECTED)
        self.assertEqual(list(actual['datasets']['team']['schema']),['label','arrived','id'])
        self.assertEqual(len(actual['datasets']['team']['rows']),5)
        self.assertEqual(actual['datasets']['team']['rows'][0]['label'],'A       ')
        self.assertEqual(len(actual['reports']['print_02.txt'].splitlines()),6)

    def test_missing_dispatch_and_exclusive_date_boundary(self):
        text=SOURCE.replace('data=team(obs=4)','data=team(obs=5)')
        report=run_plan(plan(text))['reports']['print_02.txt']
        self.assertIn('1 "Before" 1\n',report)
        self.assertIn('2 "April 1" 2\n',report)
        self.assertIn('3 "March 31" 3\n',report)
        self.assertIn('4 "After" 4\n',report)
        self.assertIn('5 "After" 5\n',report)
        self.assertIn('"ERROR"',run_plan(plan())['reports']['print_01.txt'])

    def test_directive_case_day_zero_literal_percent_and_padding(self):
        text=SOURCE.replace("'%Y|%b|%0d   '","'[%d/%0d/%b/%B/%Y/%%]   '")
        report=run_plan(plan(text))['reports']['print_01.txt']
        self.assertIn('"[1/01/Apr/April/1990/%]"',report)
        self.assertNotIn(']   "',report)

    def test_print_column_order_and_observation_limit_do_not_mutate_table(self):
        value=plan(SOURCE.replace('var id label arrived;','var arrived id;').replace('data=team;','data=team(obs=1);'))
        actual=run_plan(value)
        self.assertEqual(actual['datasets'],EXPECTED['datasets'])
        self.assertTrue(actual['reports']['print_01.txt'].splitlines()[1].endswith('arrived id'))
        self.assertEqual(len(actual['reports']['print_01.txt'].splitlines()),3)

    def test_procedure_title_persists_and_reset_removes_it(self):
        text=SOURCE.replace("title 'Intervals';\n",'')
        self.assertTrue(run_plan(plan(text))['reports']['print_02.txt'].startswith('TITLE: Date pictures\n'))
        text=SOURCE.replace("title 'Intervals';",'title;')
        self.assertFalse(run_plan(plan(text))['reports']['print_02.txt'].startswith('TITLE:'))

    def test_unformatted_date_is_numeric_and_character_storage_is_trimmed(self):
        text=SOURCE.replace('input label :$8. arrived :date9. id;','input label :$8. arrived :date9. id :date9.;').replace(' 1\n',' 01JAN1960\n').replace(' 2\n',' 02JAN1960\n').replace(' 3\n',' 03JAN1960\n').replace(' 4\n',' 04JAN1960\n').replace(' 5\n',' 05JAN1960\n')
        self.assertIn('1 0 "A"',run_plan(plan(text))['reports']['print_01.txt'])

    def test_source_refusals_do_not_leak_into_old_profile(self):
        for old,new in [('usr_iso','date'),('usr_iso','usr_bad1'),('var id label arrived','var id id arrived'),
                        ('var id label arrived','var missing label arrived'),('format arrived usr_iso.','format id usr_iso.'),
                        ('format arrived usr_iso.','format arrived arrived usr_iso.'),('format arrived usr_iso.','format arrived absent.'),
                        ('obs=4','obs=0'),('obs=4','obs=1001'),('obs=4','obs=1.5'),('proc print data=team;','proc print data=team noobs;'),
                        ('%Y|%b|%0d','%y|%b|%0d'),('datatype=date','datatype=datetime'),('datatype=date','datatype=date noedit'),
                        ("'Before'","'Before 2'"),("'Before'","'&name'"),("'Before'","''"),
                        ("'01APR1990'd","'01APR90'd"),("'01APR1990'd-'31MAR1993'd","'31MAR1989'd-'31MAR1993'd"),
                        ('infile cards','infile cards dsd'),('A 31DEC1989 1','A 31FEB1989 1')]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))
        self.refuse(SOURCE+'proc sort data=team out=changed;by id;run;')
        self.refuse(SOURCE+'data changed;set team;run;')

    def test_definition_options_must_validate_even_if_unused(self):
        for template in ('%m','%B'*20,'X'*41):
            text=SOURCE+"proc format;picture usr_unused low-high='"+template+"' (datatype=date);run;"
            with self.subTest(template=template):self.refuse(text)

    def test_picture_template_documented_length_boundary(self):
        value=SOURCE.replace("'%Y|%b|%0d   '","'"+'X'*40+"'")
        self.assertIn('"'+'X'*40+'"',run_plan(plan(value))['reports']['print_01.txt'])
        self.refuse(SOURCE.replace("'%Y|%b|%0d   '","'"+'X'*41+"'"))

    def test_gaps_need_other_overlap_and_other_order_refuse(self):
        value=plan();args=value['steps'][0]['operations'][0]['args'];args['ranges'][0]['lower']+=1
        with self.assertRaises(ValueError):run_plan(value)
        value=plan();args=value['steps'][3]['operations'][0]['args'];args['ranges'][1]['lower']-=1
        with self.assertRaises(ValueError):run_plan(value)
        self.refuse(SOURCE.replace("other='After'", "other='After' low-high='Bad'"))
        self.refuse(SOURCE.replace("other='After'", "other='After' other='Again'"))

    def test_exact_portable_types_and_fields(self):
        mutations=[]
        for key,value in [('version',True),('version',1),('steps',()),('tickets',[{}]),('matched',[{'kind':'picture_data'}]),('extra',1)]:
            item=plan();item[key]=value;mutations.append(item)
        for key,value in [('kind','date_print'),('inputs',[]),('line',True),('where',{}),('extra',None)]:
            item=plan();item['steps'][2][key]=value;mutations.append(item)
        for key,value in [('obs',True),('obs',1.),('obs','1'),('columns',()),('bound',[]),('title_change',[1]),('extra',False)]:
            item=plan();item['steps'][2]['operations'][0]['args'][key]=value;mutations.append(item)
        for key,value in [('datatype',1),('template',False),('extra',None)]:
            item=plan();item['steps'][0]['operations'][0]['args']['ranges'][0]['render'][key]=value;mutations.append(item)
        for item in mutations:
            with self.subTest(item=item),self.assertRaises((ValueError,RuntimeError)):run_plan(item)

    def test_hidden_marker_cycles_catalog_and_partial_program_refuse(self):
        value=compile_plan('data _null_;x=1;run;').to_dict();value['steps'][0]['operations'][0]['args']['hidden']={'kind':'date_picture'}
        with self.assertRaises(ValueError):run_plan(value)
        value=plan();value['matched'].append(value)
        with self.assertRaises(ValueError):run_plan(value)
        with self.assertRaises(ValueError):run_plan(plan(),{'outside':{}})
        value=plan();value['tickets']=[{'reason':'test'}]
        with self.assertRaises(ValueError):run_plan(value,allow_partial=True)

    def test_symbolic_date_roles_and_open_high_refuse(self):
        old="picture usr_iso low-high='%Y|%b|%0d   ' (datatype=date);"
        for new in ["picture usr_iso low-'30DEC3999'd='%Y' (datatype=date) high-high='Last';",
                    "picture usr_iso low-low='First' '02JAN1753'd-high='%Y' (datatype=date);",
                    "picture usr_iso low-<high='%Y' (datatype=date) '31DEC3999'd-high='Last';"]:
            with self.subTest(new=new):self.refuse(SOURCE.replace(old,new))

    def test_data_definition_print_and_title_counts(self):
        text=SOURCE.split('proc print data=team;',1)[0]
        for i in range(7):text+=producer([],name='d'+str(i))
        plan(text);self.refuse(text+producer([],name='excess'))
        text=SOURCE.split('proc print data=team;',1)[0]
        for i in range(7):text+="proc format;picture usr_"+chr(97+i)+" low-high='%Y' (datatype=date);run;"
        plan(text);self.refuse(text+"proc format;picture usr_excess low-high='%Y' (datatype=date);run;")
        text=SOURCE+'title;\n'*30;plan(text);self.refuse(text+'title;')
        self.refuse(SOURCE+'proc print data=team;var arrived;format arrived usr_iso.;run;')

    def test_producers_and_definitions_are_validated_without_reports(self):
        text=SOURCE.split('proc print data=team;',1)[0];plan(text)
        self.refuse(text.replace('31DEC1989','31FEB1989'))
        self.refuse(text.replace("'%Y|%b|%0d   '","'%m'"))
        self.refuse(text.replace('data team;','data team(drop=id);'))

    def test_empty_and_maximum_input_and_character_bounds(self):
        definition="proc format;picture usr_year low-high='%Y' (datatype=date);run;\n"
        self.assertEqual(run_plan(plan(definition+producer([])))['datasets']['owned']['rows'],[])
        self.assertEqual(len(run_plan(plan(definition+producer(['.']*1000)))['datasets']['owned']['rows']),1000)
        self.refuse(definition+producer(['.']*1001))
        self.assertEqual(len(run_plan(plan(definition+producer([],columns='d :date9. '+' '.join('n'+str(i) for i in range(31)))))['datasets']['owned']['schema']),32)
        self.refuse(definition+producer([],columns='d :date9. '+' '.join('n'+str(i) for i in range(32))))

    def test_state_is_job_local_and_cpp_refuses(self):
        run_plan(plan());self.assertTrue(cpp(SOURCE).blocked)
        no_titles=SOURCE.replace("title 'Date pictures';",'').replace("title 'Intervals';",'')
        self.assertFalse(run_plan(plan(no_titles))['reports']['print_01.txt'].startswith('TITLE:'))
        self.refuse(SOURCE.replace(SOURCE.split('data team;',1)[0],'',1))

    def test_preflight_does_not_render_and_late_failure_discards_first_report(self):
        value=plan(late_failure())
        with patch.object(picture,'field',side_effect=AssertionError('render during preflight')):picture.validate_program(value)
        seen=[];original=picture.validate_reports
        def observer(reports):
            result=original(reports);seen.append(len(reports));return result
        with patch.object(picture,'validate_reports',observer):job=build_job(late_failure())
        self.assertEqual(seen,[1]);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        with tempfile.TemporaryDirectory(prefix='saschi-picture-atomic-') as temporary:
            area=Path(temporary);source=area/'owned.sas';source.write_text(late_failure())
            run=subprocess.run([sys.executable,'-m','saschi','run',str(source),'--output',str(area/'job')],cwd=ROOT,capture_output=True,text=True,timeout=120)
            self.assertEqual(run.returncode,1,run.stderr)
            record=json.loads((area/'job'/'receipt.json').read_text());self.assertFalse(record['accepted'])
            for name in ('reports','exports','result.json','observed.json'):self.assertFalse((area/'job'/name).exists())


if __name__=='__main__':unittest.main()
