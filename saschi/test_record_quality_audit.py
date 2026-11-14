"""Whole record-quality audit, reason snapshots and follow-on review queue."""
import json,unittest
from examples.verify_record_quality_audit import GATE
from .stateful_target_test_support import StatefulTargetContract
from .expression_test_support import execute
from .runtime import run_plan


class RecordQualityAuditTests(StatefulTargetContract,unittest.TestCase):
    gate=GATE;phase='decision-groups-and-output';rule='DS-123'

    def test_original_row_fates_and_order_are_complete(self):
        rows=run_plan(self.original(),json.loads(GATE.inputs.read_text()))['datasets']
        self.assertEqual([(r['row_id'],r['reason'].rstrip()) for r in rows['quality_audit']['rows']],[(1,'ACCEPT'),(2,'IDENTIFIER'),(2,'MEASUREMENT'),(3,'IDENTIFIER'),(3,'MEASUREMENT'),(4,'MEASUREMENT'),(5,'MEASUREMENT'),(6,'ACCEPT'),(7,'ACCEPT')])
        self.assertEqual([r['row_id'] for r in rows['review_queue']['rows']],[2,2,3,3,4,5])
        self.assertEqual([r['record_key'] for r in rows['quality_audit']['rows'] if r['reason'].rstrip()=='ACCEPT'],['A1'.ljust(24),'E5'.ljust(24),'F6'.ljust(24)])

    def test_whole_target_handles_empty_identifier_and_all_missing_measures(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['submissions']['rows']=[{'row_id':1,'raw_id':'""','value':None,'lower':None,'upper':None}]
        result=execute(GATE.source.read_text(),inputs)['datasets']
        self.assertEqual([r['reason'].rstrip() for r in result['quality_audit']['rows']],['IDENTIFIER','MEASUREMENT'])
        self.assertEqual(result['quality_audit']['rows'],result['review_queue']['rows'])
        self.assertEqual(result['quality_audit']['rows'][0]['record_key'],' '*24)

    def test_late_key_buffer_failure_after_accepted_prefix_is_atomic(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['submissions']['schema']['raw_id']['length']=32
        inputs['submissions']['rows']=inputs['submissions']['rows'][:1]+[{'row_id':2,'raw_id':'a'*25,'value':1,'lower':0,'upper':2}]
        self.atomic_cli("data prior;x=1;put 'prefix';run;"+GATE.source.read_text(),inputs,'buffer')

    def test_missing_input_descriptor_refuses_even_with_no_rows(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['submissions']['rows']=[];inputs['submissions']['schema'].pop('upper')
        with self.assertRaises(ValueError):execute(GATE.source.read_text(),inputs)
