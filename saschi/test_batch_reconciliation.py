"""Whole batch reconciliation, per-group state and follow-on review filter."""
import json,unittest
from examples.verify_batch_reconciliation import GATE
from .stateful_target_test_support import StatefulTargetContract
from .expression_test_support import execute
from .runtime import run_plan


class BatchReconciliationTests(StatefulTargetContract,unittest.TestCase):
    gate=GATE;phase='ordered-by-groups';rule='DS-126'

    def test_complete_original_summary_and_review_fates(self):
        data=run_plan(self.original(),json.loads(GATE.inputs.read_text()))['datasets'];rows=data['batch_summary']['rows']
        self.assertEqual([(r['batch'],r['seen'],r['accepted'],r['rejected'],r['net'],r['magnitude'],r['worst'],r['status'].rstrip()) for r in rows],[(101,3,2,1,-1,5,3,'REVIEW'),(102,2,2,0,0,2,1,'READY'),(103,1,0,1,0,0,0,'REVIEW'),(104,1,1,0,0,0,0,'READY'),(105,2,1,1,2,2,2,'REVIEW')])
        self.assertEqual([r['batch'] for r in data['review_batches']['rows']],[101,103,105])
        self.assertIsNone(rows[-1]['delta']);self.assertEqual(rows[-1]['net'],2)
        self.assertEqual(rows[0]['delta'],-3)

    def test_missing_key_singleton_and_exact_limit_boundary(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['ledger']['rows']=[{'batch':None,'label':' x ','amount':3,'expected':1,'limit':2}]
        result=execute(GATE.source.read_text(),inputs)['datasets'];rows=result['batch_summary']['rows']
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['batch']);self.assertEqual(rows[0]['status'],'READY   ')
        self.assertEqual(result['review_batches']['rows'],[])

    def test_unsorted_whole_target_refuses_atomically(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['ledger']['rows'][0]['batch']=106
        self.atomic_cli("data prior;x=1;put 'prefix';run;"+GATE.source.read_text(),inputs,'sorted')

    def test_last_row_missing_does_not_reuse_scratch_delta(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['ledger']['rows']=inputs['ledger']['rows'][-2:]
        row=execute(GATE.source.read_text(),inputs)['datasets']['batch_summary']['rows'][0]
        self.assertEqual((row['seen'],row['accepted'],row['rejected'],row['net'],row['magnitude'],row['worst']),(2,1,1,2,2,2))
        self.assertIsNone(row['delta']);self.assertIsNone(row['amount'])

    def test_late_accumulator_overflow_after_prior_group_is_atomic(self):
        inputs=json.loads(GATE.inputs.read_text());inputs['ledger']['rows']=[{'batch':1,'label':'ok','amount':1,'expected':1,'limit':2},{'batch':2,'label':'large','amount':600000,'expected':0,'limit':2},{'batch':2,'label':'large','amount':600000,'expected':0,'limit':2}]
        self.atomic_cli("data prior;x=1;put 'prefix';run;"+GATE.source.read_text(),inputs,'magnitude')
