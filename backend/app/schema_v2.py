"""Frozen relational schema used exclusively by Alembic revision 0002."""
import json
from pathlib import Path
import sqlalchemy as sa
metadata=sa.MetaData()
for record in json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8')):
    columns=[]
    for column in record['columns']:
        kind=getattr(sa,column['type'])
        datatype=kind(column['precision'],column['scale']) if column['type']=='Numeric' else kind(column['length']) if column['length'] else kind()
        foreign=[sa.ForeignKey(column['foreign_key'],name=column['fk_name'],use_alter=column['use_alter'])] if column['foreign_key'] else []
        columns.append(sa.Column(column['name'],datatype,*foreign,primary_key=column['primary_key'],nullable=column['nullable']))
    table=sa.Table(record['name'],metadata,*columns,*(sa.UniqueConstraint(*keys) for keys in record['unique']),*(sa.CheckConstraint(c['sql'],name=c['name']) for c in record['checks']))
    for index in record['indexes']:
        sa.Index(index['name'],*(table.c[key] for key in index['columns']),unique=index['unique'])
