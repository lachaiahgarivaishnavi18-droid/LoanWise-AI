"""Load the immutable schema snapshot used by migration 0001, independent of ORM evolution."""
import json
from pathlib import Path
from sqlalchemy import MetaData, Table, Column, Integer, Float, Double, String, Boolean, JSON, Text, ForeignKey, UniqueConstraint, Index
metadata = MetaData()
types = {'Integer': Integer, 'Float': Float, 'Double': Double, 'String': String, 'Boolean': Boolean, 'JSON': JSON, 'Text': Text}
for record in json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8')):
    columns = []
    for col in record['columns']:
        kind = types[col['type']](col['length']) if col['length'] else types[col['type']]()
        foreign = [ForeignKey(col['foreign_key'])] if col['foreign_key'] else []
        columns.append(Column(col['name'], kind, *foreign, primary_key=col['primary_key'], nullable=col['nullable']))
    table = Table(record['name'], metadata, *columns, *(UniqueConstraint(*keys) for keys in record['unique']))
    for index in record['indexes']:
        Index(index['name'], *(table.c[key] for key in index['columns']), unique=index['unique'])
