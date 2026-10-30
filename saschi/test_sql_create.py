"""Portable descriptor attacks and bounded SQL source/integration acceptance."""
from copy import deepcopy
import contextlib
import io
import tempfile
from pathlib import Path
import unittest

from .sql_create import parse_create,validate_step,validate_columns,materialize,RESERVED
from .compare import equal
from examples.verify_sql_create import (PINS,REFUSALS,ORIGINAL,CORPUS,SOURCE_PINS,
    step_for,table_for,columns,program,program_witness,original_expected,corpus_expected,
    execute,cli_check,naive_controls)


class SQLCreateHelperTests(unittest.TestCase):
    def test_hand_pins_and_source_refusals(self):
        for text,expected in PINS:self.assertEqual(parse_create(text),expected)
        for text in REFUSALS:
            with self.subTest(text=text[:80]),self.assertRaises(ValueError):parse_create(text)

    def test_keyword_policy_applies_case_insensitively_to_table_and_columns(self):
        for name in RESERVED:
            for text in ('create table '+name.upper()+' (a char(8))','create table t ('+name.upper()+' char(8))'):
                with self.assertRaises(ValueError):parse_create(text)

    def test_exact_empty_table_shape_and_fresh_descriptor_objects(self):
        step=step_for('t',columns(('z',2),('a',8)));before=deepcopy(step)
        table=materialize(step,{})
        self.assertEqual(table,{'schema':{'z':{'type':'character','length':2},'a':{'type':'character','length':8}},'rows':[]})
        self.assertEqual(list(table['schema']),['z','a'])
        table['schema']['z']['length']=99;table['rows'].append({'z':'x','a':'y'})
        self.assertEqual(step,before);self.assertEqual(materialize(step,{}),table_for(before['operations'][0]['args']['columns']))

    def test_destination_refusal_is_case_insensitive_and_nonmutating(self):
        step=step_for('t',columns(('a',8)))
        for rows in ([],[{'x':2.}]):
            catalog={'T':{'schema':{'x':'number'},'rows':rows}};before=deepcopy(catalog)
            with self.assertRaisesRegex(ValueError,'existing destination'):materialize(step,catalog)
            self.assertEqual(catalog,before)

    def test_unrelated_catalog_is_not_mutated_or_copied_into_new_table(self):
        catalog={'raw':{'schema':{'x':'number'},'rows':[{'x':2.}],'label':'retained'}};before=deepcopy(catalog)
        table=materialize(step_for('t',columns(('a',8))),catalog)
        self.assertEqual(catalog,before);self.assertEqual(set(table),{'schema','rows'})

    def test_version_is_exactly_integer_two(self):
        for version in (1,3,True,False,2.,'2',None):
            with self.assertRaises(ValueError):validate_step(step_for('t',columns(('a',8))),version)

    def test_step_metadata_and_extra_fields_refuse(self):
        template=step_for('t',columns(('a',8)))
        changes={'kind':'data','name':'T','line':False,'inputs':['raw'],'by':['a'],
                 'nodupkey':True,'where':{},'retained':{'a':0},'lengths':{'a':8},
                 'display_names':{'a':'A'},'extra':True}
        for key,value in changes.items():
            step=deepcopy(template);step[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_step(step)
        for key in ('inputs','by','retained','lengths','display_names'):
            step=deepcopy(template);step[key]=() if key in ('inputs','by') else []
            with self.assertRaises(ValueError):validate_step(step)

    def test_missing_step_fields_and_bad_operations_refuse(self):
        template=step_for('t',columns(('a',8)))
        for key in template:
            step=deepcopy(template);del step[key]
            with self.subTest(key=key),self.assertRaises(ValueError):validate_step(step)
        for operations in ([],(),[{}],[deepcopy(template['operations'][0])]*2):
            step=deepcopy(template);step['operations']=operations
            with self.assertRaises(ValueError):validate_step(step)

    def test_operation_exact_shape_and_source_line_order(self):
        template=step_for('t',columns(('a',8)),line=3,create_line=4)
        for key,value in [('kind','assign'),('line',True),('line',2),('line','4'),('extra',1),('args',{})]:
            step=deepcopy(template);step['operations'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_step(step)
        step=deepcopy(template);step['operations'][0]['args']['extra']=1
        with self.assertRaises(ValueError):validate_step(step)

    def test_column_exact_shape_normalization_and_length(self):
        for value in ([],(),[{}],[{'name':'a','type':'number','length':8}],
            [{'name':'A','type':'character','length':8}],[{'name':'a','type':'character','length':True}],
            [{'name':'a','type':'character','length':8.}],[{'name':'a','type':'character','length':0}],
            [{'name':'a','type':'character','length':32768}],[{'name':'a','type':'character','length':8,'label':'x'}],
            columns(('a',8),('a',2)),columns(*[(f'c{i}',1) for i in range(65)])):
            with self.subTest(value=str(value)[:80]),self.assertRaises(ValueError):validate_columns(value)

    def test_cyclic_or_deep_hostile_values_fail_without_recursive_materialization(self):
        for position in ('columns','name','extra'):
            step=step_for('t',columns(('a',8)))
            if position=='columns':step['operations'][0]['args']['columns'].append(step)
            elif position=='name':step['operations'][0]['args']['columns'][0]['name']=step
            else:step['extra']=step
            with self.assertRaises(ValueError):validate_step(step)

    def test_five_competing_empty_descriptor_interpretations_are_detected(self):
        self.assertEqual(naive_controls(),5)

    def test_independent_R_consumes_original_and_unchanged_postal_source(self):
        self.assertTrue(equal(program_witness(ORIGINAL),(original_expected(),{'statements':6,'tables':['contacts','widths'],'rows':0}),ordered_maps=True))
        self.assertTrue(equal(program_witness(CORPUS),(corpus_expected(),{'statements':3,'tables':['address'],'rows':0}),ordered_maps=True))


class SQLCreateIntegrationTests(unittest.TestCase):
    def test_original_and_complete_unchanged_corpus_source(self):
        from examples.verify_sql_create import check_program
        check_program(ORIGINAL,original_expected(),6);check_program(CORPUS,corpus_expected(),3)

    def test_new_step_does_not_change_old_plan_shapes(self):
        from .plan import compile_plan
        p=compile_plan(program('create table t (z char(2),a char(8))'))
        self.assertFalse(p.blocked,p.tickets)
        self.assertEqual(p.to_dict()['steps'],[step_for('t',columns(('z',2),('a',8)),line=1,create_line=1)])
        old=compile_plan('data d;x=1;run;').to_dict()['steps'][0]
        self.assertEqual(old['kind'],'data');self.assertEqual(len(old['operations']),1)

    def test_canonical_source_whitespace_and_standalone_helper_cap_are_distinct(self):
        from examples.verify_sql_create import HELPER_RESOURCE_REFUSAL
        with self.assertRaises(ValueError):parse_create(HELPER_RESOURCE_REFUSAL)
        self.assertEqual(execute(program(HELPER_RESOURCE_REFUSAL))[0],
                         {'datasets':{'t':table_for(columns(('a',8)))},'log':[]})

    def test_sql_procedure_boundary_and_full_source_consumption(self):
        from .plan import compile_plan
        for source in ('proc sql noexec;create table t (a char(8));quit;',
            'proc sql;quit;','proc sql;create table t (a char(8));run;',
            'proc sql;create table t (a char(8));','proc sql;create table t (a char(8));quit',
            'create table t (a char(8));','proc sql;create table t (a char(8));create table u (a char(8));quit;',
            'proc sql;create table t (a char(8));insert into t values (1);quit;',
            'proc sql;create table t (a char(8));quit;proc print;run;',
            'proc sql;create table t (a char(8));quit;orphan=1;'):
            self.assertTrue(compile_plan(source).blocked,source)

    def test_existing_destination_refuses_including_same_run_duplicate(self):
        from .plan import compile_plan
        from .runtime import run_plan
        source=program('create table t (a char(8))');p=compile_plan(source)
        for rows in ([],[{'x':2.}]):
            supplied={'T':{'schema':{'x':'number'},'rows':rows}};before=deepcopy(supplied)
            with self.assertRaises(ValueError):run_plan(p.to_dict(),supplied)
            self.assertEqual(supplied,before)
        duplicated=compile_plan(source+source.upper())
        self.assertFalse(duplicated.blocked,duplicated.tickets)
        with self.assertRaises(ValueError):run_plan(duplicated.to_dict())

    def test_empty_created_character_descriptor_composes_with_supplied_set(self):
        result,_=execute(program('create table empty (tag char(4))')+'data copied;set empty;run;')
        self.assertEqual(result,{'datasets':{'empty':{'schema':{'tag':{'type':'character','length':4}},'rows':[]},
            'copied':{'schema':{'tag':{'type':'character','length':4}},'rows':[]}},'log':[]})

    def test_portable_sql_descriptor_attack_is_rejected_on_no_rows(self):
        from .plan import compile_plan
        from .runtime import run_plan
        p=compile_plan(program('create table t (a char(8))')).to_dict()
        for key,value in [('type','number'),('length',False),('length',32768),('name','_n_'),('extra',True)]:
            forged=deepcopy(p);forged['steps'][0]['operations'][0]['args']['columns'][0][key]=value
            with self.assertRaises(ValueError):run_plan(forged)

    def test_cpp_remains_refused(self):
        from .job import build_job
        self.assertEqual(build_job(program('create table t (a char(8))'),target='cpp').code,2)

    def test_late_destination_failure_discards_earlier_log_and_result(self):
        from .emit_py import translate
        source='data earlier;put "EARLIER";run;'+program('create table t (a char(8))')
        supplied={'t':{'schema':{'x':'number'},'rows':[]}}
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':supplied})
        self.assertEqual(stream.getvalue(),'')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.sas';path.write_text(source);cli_check(path,None,supplied)

    def test_actual_job_comparator_rejects_all_five_naive_descriptors(self):
        self.assertEqual(naive_controls(actual_jobs=True),5)


if __name__=='__main__':unittest.main()
