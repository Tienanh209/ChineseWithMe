"""The SQL migration is the schema's source of truth. This fails when an ORM model and the
migrated database disagree on tables, columns, types, nullability, defaults, keys or FKs."""

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.models import Base

DIALECT = postgresql.dialect()


def _reflect(sync_conn):
    insp = inspect(sync_conn)
    return {
        name: {
            "columns": {c["name"]: c for c in insp.get_columns(name)},
            "pk": set(insp.get_pk_constraint(name)["constrained_columns"]),
            "fks": {
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                    fk["options"].get("ondelete"),
                )
                for fk in insp.get_foreign_keys(name)
            },
        }
        for name in insp.get_table_names()
    }


async def test_models_match_migrated_schema(db):
    reflected = await (await db.connection()).run_sync(_reflect)
    assert set(reflected) - {"schema_migrations"} == set(Base.metadata.tables)

    problems = []
    for name, table in Base.metadata.tables.items():
        db_table = reflected[name]
        if set(db_table["columns"]) != set(table.columns.keys()):
            problems.append(f"{name}: columns db={sorted(db_table['columns'])} model={sorted(table.columns.keys())}")
            continue
        for col in table.columns:
            r = db_table["columns"][col.name]
            where = f"{name}.{col.name}"
            if col.type.compile(DIALECT) != r["type"].compile(DIALECT):
                problems.append(f"{where}: type db={r['type'].compile(DIALECT)} model={col.type.compile(DIALECT)}")
            if col.nullable != r["nullable"]:
                problems.append(f"{where}: nullable db={r['nullable']} model={col.nullable}")
            if (col.computed is not None) != ("computed" in r):
                problems.append(f"{where}: generated column mismatch")
            db_has_default = r["default"] is not None or "identity" in r or "computed" in r
            model_has_default = col.server_default is not None or col.identity is not None or col.computed is not None
            if db_has_default != model_has_default:
                problems.append(f"{where}: default db={db_has_default} model={model_has_default}")
        if db_table["pk"] != set(table.primary_key.columns.keys()):
            problems.append(f"{name}: primary key db={db_table['pk']}")
        model_fks = {
            (
                tuple(c.name for c in fk.columns),
                fk.referred_table.name,
                tuple(e.column.name for e in fk.elements),
                fk.ondelete,
            )
            for fk in table.foreign_key_constraints
        }
        if db_table["fks"] != model_fks:
            problems.append(f"{name}: foreign keys db={db_table['fks']} model={model_fks}")
    assert not problems, "\n".join(problems)
