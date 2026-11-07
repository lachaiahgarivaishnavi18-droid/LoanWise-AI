"""Developer utility: regenerate ONLY when creating a new numbered migration snapshot."""
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.database import Base
from app import models
from sqlalchemy import UniqueConstraint, CheckConstraint

parser=argparse.ArgumentParser()
parser.add_argument('--version',required=True,choices=['v2'])
args=parser.parse_args()

output = []
for table in Base.metadata.sorted_tables:
    output.append({'name': table.name, 'columns': [{'name': c.name, 'type': type(c.type).__name__, 'length': getattr(c.type, 'length', None), 'precision':getattr(c.type,'precision',None),'scale':getattr(c.type,'scale',None),'primary_key': c.primary_key, 'nullable': c.nullable, 'foreign_key': next((fk.target_fullname for fk in c.foreign_keys), None),'fk_name':next((fk.name for fk in c.foreign_keys),None),'use_alter':any(fk.use_alter for fk in c.foreign_keys)} for c in table.columns], 'unique': [[c.name for c in constraint.columns] for constraint in table.constraints if isinstance(constraint, UniqueConstraint)],'checks':[{'name':c.name,'sql':str(c.sqltext)} for c in table.constraints if isinstance(c,CheckConstraint)], 'indexes': [{'name': idx.name, 'columns': [c.name for c in idx.columns], 'unique': idx.unique} for idx in table.indexes]})
Path(__file__).resolve().parents[1].joinpath(f'backend/app/schema_{args.version}.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
