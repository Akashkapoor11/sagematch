import json
from typing import Iterable, List

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, Text, create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from .config import DATABASE_URL
from .models import Product

metadata = MetaData()

products_table = Table(
    'products', metadata,
    Column('id', String(255), primary_key=True),
    Column('name', String(255), nullable=False),
    Column('category', String(255), nullable=False),
    Column('description', Text, nullable=False, server_default=''),
    Column('team_size_min', Integer, nullable=True),
    Column('team_size_max', Integer, nullable=True),
    Column('integrations', JSON, nullable=False),
    Column('features', JSON, nullable=False),
    Column('deployment', JSON, nullable=False),
    Column('pricing_tier', String(100), nullable=False, server_default=''),
    Column('website', Text, nullable=False, server_default=''),
    Column('source_row', Integer, nullable=True),
    Column('extra_fields', JSON, nullable=False),
)

metadata_table = Table(
    'metadata', metadata,
    Column('key', String(255), primary_key=True),
    Column('value', JSON, nullable=False),
)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        kwargs = {'future': True, 'pool_pre_ping': True}
        if DATABASE_URL.startswith('sqlite'):
            kwargs.update({'connect_args': {'check_same_thread': False}, 'poolclass': StaticPool})
        _engine = create_engine(DATABASE_URL, **kwargs)
    return _engine


def reset_engine_for_tests():
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db():
    metadata.create_all(get_engine())


def replace_products(products: Iterable[Product], quality_report=None):
    init_db()
    rows = [
        {
            'id': p.id,
            'name': p.name,
            'category': p.category,
            'description': p.description or '',
            'team_size_min': p.team_size_min,
            'team_size_max': p.team_size_max,
            'integrations': list(p.integrations),
            'features': list(p.features),
            'deployment': list(p.deployment),
            'pricing_tier': p.pricing_tier or '',
            'website': p.website or '',
            'source_row': p.source_row,
            'extra_fields': dict(p.extra_fields),
        }
        for p in products
    ]
    with get_engine().begin() as conn:
        conn.execute(delete(products_table))
        if rows:
            conn.execute(products_table.insert(), rows)
        if quality_report is not None:
            # Portable upsert: delete then insert within the same transaction.
            conn.execute(delete(metadata_table).where(metadata_table.c.key == 'quality_report'))
            conn.execute(metadata_table.insert().values(key='quality_report', value=quality_report))


def get_quality_report():
    init_db()
    with get_engine().connect() as conn:
        row = conn.execute(
            select(metadata_table.c.value).where(metadata_table.c.key == 'quality_report')
        ).first()
    return row[0] if row else None


def _to_product(row) -> Product:
    return Product(
        id=row.id,
        name=row.name,
        category=row.category,
        description=row.description or '',
        team_size_min=row.team_size_min,
        team_size_max=row.team_size_max,
        integrations=list(row.integrations or []),
        features=list(row.features or []),
        deployment=list(row.deployment or []),
        pricing_tier=row.pricing_tier or '',
        website=row.website or '',
        source_row=row.source_row,
        extra_fields=dict(row.extra_fields or {}),
    )


def list_products() -> List[Product]:
    init_db()
    with get_engine().connect() as conn:
        rows = conn.execute(select(products_table).order_by(products_table.c.name)).mappings().all()
    return [_to_product(row) for row in rows]
