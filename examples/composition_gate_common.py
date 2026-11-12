"""Whole-program R expectations and generated cross-family input controls."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import tempfile

from wave_gate_common import FamilyGate,decode


class CompositionGate(FamilyGate):
    def witness(self,inputs):
        assert hashlib.sha256(self.source.read_bytes()).hexdigest()==self.source_sha
        expected=json.loads(self.expected.read_text());actual=deepcopy(expected)
        for table in actual['datasets'].values():table['rows']=[]
        actual['log']=[];table=inputs['raw']
        assert table['schema']==json.loads(self.inputs.read_text())['raw']['schema']
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.csv'
            with path.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(table['schema'])
                writer.writerows([row[name] for name in table['schema']] for row in table['rows'])
            records=self.rrun('program',self.source,path)
        assert records[0]=='STATEMENTS|'+str(self.statements)
        for record in records[1:]:
            parts=record.split('|')
            if parts[0]=='ROW':
                schema=actual['datasets'][parts[1]]['schema'];assert len(parts[2:])==len(schema)
                actual['datasets'][parts[1]]['rows'].append(dict(zip(schema,map(decode,parts[2:]))))
            elif parts[0]=='LOG':actual['log'].append(bytes.fromhex(parts[1]).decode('ascii'))
            else:raise AssertionError(record)
        return actual
