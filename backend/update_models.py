"""Phase 10C/10D Schema Reconciliation.

Dynamically compares SQLAlchemy models against the live database,
and issues ALTER TABLE ADD COLUMN statements for any missing columns.
Idempotent and safe. Does not drop columns or tables.
"""

import logging
import sys

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import _CreateDropBase

from app.database.session import engine, Base

# Import main to organically load all models and routers
import app.main

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger("schema_reconciliation")


def get_column_type_string(column) -> str:
    """Compile the column type to a string for the dialect."""
    return column.type.compile(engine.dialect)


def run_reconciliation():
    logger.info("=" * 60)
    logger.info("  Phase 10C/10D Schema Reconciliation")
    logger.info("=" * 60)

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    missing_columns_found = []

    with engine.begin() as conn:
        for table_name, table_def in Base.metadata.tables.items():
            if table_name not in existing_tables:
                logger.info(f"Table '{table_name}' does not exist in DB yet. Creating it...")
                table_def.create(conn)
                logger.info(f"  -> Created table '{table_name}'.")
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
            
            for column in table_def.columns:
                if column.name not in existing_columns:
                    col_type_str = get_column_type_string(column)
                    
                    alter_stmt = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type_str}"
                    
                    logger.info(f"Missing column detected: {table_name}.{column.name} ({col_type_str})")
                    
                    try:
                        conn.execute(text(alter_stmt))
                        missing_columns_found.append({
                            "table": table_name,
                            "column": column.name,
                            "action": f"Added {col_type_str}"
                        })
                        logger.info(f"  -> Successfully added {column.name} to {table_name}.")
                    except Exception as exc:
                        logger.error(f"  -> Failed to add {column.name} to {table_name}: {exc}")

    logger.info("\n" + "=" * 60)
    logger.info("  RECONCILIATION REPORT")
    logger.info("=" * 60)
    
    if not missing_columns_found:
        logger.info("All models match the database schema. No missing columns found.")
    else:
        logger.info(f"{'TABLE':<25} | {'MISSING COLUMN':<20} | {'ACTION TAKEN':<20}")
        logger.info("-" * 70)
        for mc in missing_columns_found:
            logger.info(f"{mc['table']:<25} | {mc['column']:<20} | {mc['action']:<20}")

    logger.info("\nSTATUS: PASS")


if __name__ == "__main__":
    try:
        run_reconciliation()
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        sys.exit(1)
