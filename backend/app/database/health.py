from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import Base, engine


database_startup_error: str | None = None


def initialize_database() -> None:
    global database_startup_error

    try:
        Base.metadata.create_all(bind=engine)
        apply_schema_updates()
        database_startup_error = None
    except SQLAlchemyError as exc:
        database_startup_error = str(exc.__cause__ or exc)


def apply_schema_updates() -> None:
    statements = (
        "alter table requests add column if not exists session_id varchar(64)",
        "alter table requests add column if not exists provider_used varchar(64)",
        "alter table requests add column if not exists original_provider varchar(64)",
        "alter table requests add column if not exists fallback_used boolean default false",
        "alter table requests add column if not exists model_used varchar(128)",
        "alter table requests add column if not exists latency_ms integer",
        "alter table requests add column if not exists request_category varchar(64)",
        "alter table requests add column if not exists request_priority varchar(64)",
        "alter table requests add column if not exists request_status varchar(64) default 'success'",
        "alter table requests add column if not exists lifecycle_state varchar(64) default 'completed'",
        "alter table requests add column if not exists received_at timestamptz",
        "alter table requests add column if not exists queued_at timestamptz",
        "alter table requests add column if not exists scheduled_at timestamptz",
        "alter table requests add column if not exists execution_started_at timestamptz",
        "alter table requests add column if not exists provider_response_at timestamptz",
        "alter table requests add column if not exists completed_at timestamptz",
        "alter table requests add column if not exists queue_wait_ms integer",
        "alter table requests add column if not exists execution_duration_ms integer",
        "alter table requests add column if not exists cache_hit boolean default false",
        "alter table requests add column if not exists error_message text",
        "create index if not exists ix_requests_session_id on requests (session_id)",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def check_database() -> tuple[bool, str | None]:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return True, None
    except SQLAlchemyError as exc:
        return False, str(exc.__cause__ or exc)
