"""DS-105 exact positions, word boundaries and zero-length extraction."""
from copy import deepcopy
import contextlib,io,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
from examples.verify_search_extraction import GATE,REFUSALS
from sas_semantics import sas_findc,sas_findw,sas_indexc,sas_indexw,sas_substrn
from .emit_py import translate
from .job import build_job
from .plan import compile_plan
from .runtime import run_plan
from .rules import route_function
from .test_do_counted import execute,job_with_inputs
ROOT=Path(__file__).resolve().parent.parent
NAMES=('findc','findw','indexc','indexw','substrn')

def catalog(rows,position='number',text=None):
    return {'raw':{'schema':{'a':text or {'type':'character','length':4},'position':position},'rows':rows}}

class SearchExtractionTests(unittest.TestCase):
    def test_independent_original_and_every_cell(self):
        GATE.qualify(REFUSALS)
        result,stdout=execute(GATE.source.read_text(),json.loads(GATE.inputs.read_text()))
        self.assertEqual(result,json.loads(GATE.expected.read_text()))
        self.assertEqual(stdout,''.join(x+'\n' for x in result['log']))

    def test_findc_case_complement_and_direction(self):
        self.assertEqual(sas_findc('ABc','ab','IK'),3)
        self.assertEqual(sas_findc('abca','a',-99),4)
        self.assertEqual(sas_findc('abca','a','I',-3),1)
        self.assertEqual(sas_findc('abca','a',0),0)
        self.assertEqual(sas_findc('abca','a',5),0)

    def test_word_substring_can_contain_delimiters(self):
        self.assertEqual(sas_findw('x a b x','a b',' '),3)
        self.assertEqual(sas_findw('ab abc ab','ab',' ',2),8)
        self.assertEqual(sas_findw('ab abc ab','ab',' ',-99),8)
        self.assertEqual(sas_findw('AB ab','ab',' ','I'),1)
        self.assertEqual(sas_findw('ababc','ab',' '),0)

    def test_index_union_and_word_edge_trimming(self):
        self.assertEqual(sas_indexc('abZ','Z','b'),2)
        self.assertEqual(sas_indexw('  ab ',' ab '),3)
        self.assertEqual(sas_indexw('   ',' '),1)
        self.assertEqual(sas_indexw('abc',' '),0)
        self.assertEqual(sas_indexw('',''),1)
        with self.assertRaises(ValueError):sas_indexw('ab,x','x',',')

    def test_substrn_interval_clipping_and_omitted_length(self):
        self.assertEqual([sas_substrn('abcd',p,n) for p,n in [(2,2),(0,3),(-1,3),(3,99),(99,2),(1,0),(1,-1)]],['bc','ab','a','cd','','',''])
        self.assertEqual(sas_substrn('abcd',-99),'abcd')
        self.assertEqual(sas_substrn('abcd',2),'bcd')
        self.assertEqual(sas_substrn('abcd',None,2),'')
        self.assertEqual(sas_substrn('abcd',2,None),'')
        with self.assertRaises(ValueError):sas_substrn('abcd',None,'x')

    def test_new_width_inherits_source_not_extract_count(self):
        result,_=execute("data d;x=substrn('abcd',2,2);y=substrn('abcd',99,2);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'bc  ','y':'    '}])
        self.assertEqual(result['datasets']['d']['schema'],{'x':{'type':'character','length':4},'y':{'type':'character','length':4}})
        result,_=execute("data d;length x $2;x=substrn('abcd',1,4);run;")
        self.assertEqual(result['datasets']['d']['rows'],[{'x':'ab'}])
        self.assertIn(build_job("data d;a=substrn('abcd',1,2);b=substr('abcd',0,2);run;").code,(1,2))

    def test_static_controls_and_types_are_checked_on_skipped_paths(self):
        rhs=["findc('x','x','Q')","findc('x','x',.)","findw('x','x')","findw('x','x','a')", "findw('x','x',' ','E')","indexw('x','x',',')",'substrn(123,1,2)',"substrn('abcd',.5,2)","indexc('x',1)"]
        for value in rhs:
            with self.subTest(value=value):self.assertEqual(build_job('data d;if 0 then x='+value+';run;').code,2)

    def test_empty_inputs_validate_both_descriptors(self):
        source='data d;set raw;if 0 then x=substrn(a,position,2);run;'
        self.assertEqual(job_with_inputs(source,catalog([],position={'type':'character','length':1})).code,1)
        self.assertEqual(job_with_inputs(source,catalog([],text='number')).code,1)
        result,_=execute(source,catalog([]))
        self.assertEqual(result['datasets']['d']['rows'],[])

    def test_dynamic_bad_position_is_lazy_or_atomic(self):
        inputs=catalog([{'a':'abcd','position':1},{'a':'abcd','position':.5}])
        result,_=execute('data d;set raw;if 0 then x=substrn(a,position,2);run;',inputs)
        self.assertEqual([row['x'] for row in result['datasets']['d']['rows']],['    ','    '])
        source="data d;set raw;x=substrn(a,position,2);output;put 'made';run;"
        self.assertEqual(job_with_inputs(source,catalog(inputs['raw']['rows'][:1])).code,0)
        job=job_with_inputs(source,inputs);self.assertEqual(job.code,1);self.assertIsNone(job.result)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),self.assertRaises(ValueError):exec(translate(source).code,{'inputs':inputs})
        self.assertEqual(stream.getvalue(),'')

    def test_actual_cli_bad_second_row_is_atomic_for_every_function(self):
        calls={'findc':"findc(a,'x')",'findw':"findw(a,'x',' ')",'indexc':"indexc(a,'x')",'indexw':"indexw(a,'x')",'substrn':'substrn(a,1,2)'}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);data=folder/'inputs.json';data.write_text(json.dumps(catalog([{'a':'x','position':1},{'a':'é','position':1}])))
            for name,call in calls.items():
                source=folder/(name+'.sas');source.write_text("data d;set raw;x="+call+";output;put 'made';run;");out=folder/('cli-'+name)
                self.assertEqual(job_with_inputs(source.read_text(),catalog([{'a':'x','position':1}])).code,0)
                run=subprocess.run([sys.executable,'-B','-m','saschi','run',str(source),'--inputs',str(data),'--output',str(out)],capture_output=True,text=True,cwd=ROOT,timeout=60)
                self.assertEqual(run.returncode,1,run.stdout+run.stderr)
                receipt=json.loads((out/'receipt.json').read_text());self.assertFalse(receipt['accepted']);self.assertEqual(receipt['tickets'],[])
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'observed.json').exists())

    def test_metadata_order_immutability_and_repeated_execution(self):
        inputs=catalog([{'a':'abcd','position':1}],text={'type':'character','length':4,'label':'Original','format':'$CHAR4.'});before=deepcopy(inputs)
        plan=compile_plan("data d;set raw;x=substrn(a,position,2);n=findc(a,'c');run;").to_dict();saved=deepcopy(plan);result=run_plan(plan,inputs)
        self.assertEqual(list(result['datasets']['d']['schema']),['a','position','x','n'])
        self.assertEqual(result['datasets']['d']['schema']['a'],inputs['raw']['schema']['a'])
        self.assertEqual((inputs,plan),(before,saved));self.assertEqual(run_plan(plan,inputs),result)

    def test_provenance_array_namespace_and_cpp(self):
        calls=["findc('x','x')","findw('x','x',' ')","indexc('x','x')","indexw('x','x')","substrn('x',1,1)"]
        for name,call in zip(NAMES,calls):
            source='data d;x='+call+';run;';plan=compile_plan(source)
            self.assertFalse(plan.blocked,plan.tickets);self.assertIn(('search-extraction','DS-105',1),plan.matched)
            self.assertEqual(route_function(source)[1],'DS-105');self.assertEqual(build_job(source,target='cpp').code,2)
            result,_=execute(f'data d;array {name} a b;a=1;b=2;x={name}[2];run;')
            self.assertEqual(result['datasets']['d']['rows'],[{'a':1.,'b':2.,'x':2.}])

    def test_malformed_portable_and_held_contexts(self):
        original=compile_plan("data d;x=substrn('x',1,1);run;").to_dict()
        for args in (None,{},(),[],[{}],[{'kind':'character','value':'x'},{'kind':'number','value':True}]):
            plan=deepcopy(original);plan['steps'][0]['operations'][0]['args']['value']['args']=args
            with self.subTest(args=args),self.assertRaises(ValueError):run_plan(plan)
        for source in ["data d;if findc('x','x') then x=1;run;",'data d;set raw;where indexw(a,\'x\');run;',"data d;retain n 0;x=substrn('x',1);run;"]:
            with self.subTest(source=source):self.assertIn(build_job(source).code,(1,2))

if __name__=='__main__':unittest.main()
