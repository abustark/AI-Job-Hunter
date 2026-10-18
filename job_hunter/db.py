import sqlite3
import re
from pathlib import Path
from contextlib import contextmanager

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
 location TEXT NOT NULL DEFAULT '', work_mode TEXT NOT NULL DEFAULT 'Unknown', source TEXT NOT NULL DEFAULT 'Manual',
 source_id TEXT, posted_at TEXT, discovered_at TEXT NOT NULL, last_seen TEXT NOT NULL, salary TEXT,
 description TEXT NOT NULL DEFAULT '', skills TEXT NOT NULL DEFAULT '', job_type TEXT, seniority TEXT,
 status TEXT NOT NULL DEFAULT 'To Review', notes TEXT NOT NULL DEFAULT '', follow_up TEXT,
 scope TEXT NOT NULL DEFAULT 'India', country TEXT, eligibility TEXT, visa_info TEXT, sponsorship TEXT, relocation TEXT,
 application_deadline TEXT,
 UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_seen ON jobs(discovered_at);
CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS scan_runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 source TEXT NOT NULL, outcome TEXT NOT NULL, fetched INTEGER DEFAULT 0, added INTEGER DEFAULT 0,
 duplicates INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS drafts (id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
 kind TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
 event TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resume_files (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, content BLOB NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_previews (token TEXT PRIMARY KEY, content TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (id INTEGER PRIMARY KEY, remote_addr TEXT NOT NULL, attempted_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_login_attempts_addr_time ON login_attempts(remote_addr, attempted_at);
"""


def is_postgres(path):
    return str(path).startswith(("postgres://", "postgresql://"))


def postgres_sql(sql):
    """Translate the small SQLite-compatible SQL subset used by the app."""
    sql = sql.strip()
    if sql.upper().startswith("PRAGMA "):
        return ""
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\s+profile\b", "INSERT INTO profile", sql, flags=re.I)
    if re.match(r"INSERT INTO profile\s*\(", sql, flags=re.I) and "ON CONFLICT" not in sql.upper():
        sql += " ON CONFLICT (id) DO NOTHING"
    sql = sql.replace(" BLOB ", " BYTEA ")
    sql = sql.replace("?", "%s")
    return sql


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, args=()):
        return self._connection.execute(postgres_sql(sql), args)


@contextmanager
def connect(path):
    if is_postgres(path):
        import psycopg
        from psycopg.rows import dict_row

        dsn = "postgresql://" + str(path).removeprefix("postgres://") if str(path).startswith("postgres://") else str(path)
        with psycopg.connect(dsn, row_factory=dict_row) as db:
            yield PostgresConnection(db)
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(path):
    if is_postgres(path):
        import psycopg
        from psycopg.rows import dict_row

        dsn = "postgresql://" + str(path).removeprefix("postgres://") if str(path).startswith("postgres://") else str(path)
        postgres_schema = SCHEMA.replace("PRAGMA foreign_keys=ON;", "")
        postgres_schema = re.sub(r"\bINTEGER PRIMARY KEY\b", "SERIAL PRIMARY KEY", postgres_schema, flags=re.I)
        postgres_schema = postgres_schema.replace("BLOB", "BYTEA").replace("INSERT OR IGNORE INTO profile", "INSERT INTO profile")
        statements = [statement.strip() for statement in postgres_schema.split(";") if statement.strip()]
        with psycopg.connect(dsn, row_factory=dict_row) as db:
            with db.cursor() as cur:
                for statement in statements:
                    if statement.upper().startswith("INSERT INTO PROFILE"):
                        statement += " ON CONFLICT (id) DO NOTHING"
                    cur.execute(statement)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_addr_time ON login_attempts(remote_addr, attempted_at)")
                for name, definition in {
                    "scope": "TEXT NOT NULL DEFAULT 'India'", "country": "TEXT", "eligibility": "TEXT",
                    "visa_info": "TEXT", "sponsorship": "TEXT", "relocation": "TEXT", "application_deadline": "TEXT",
                }.items():
                    cur.execute(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {name} {definition}")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scope ON jobs(scope)")
                for name in ("scope", "country"):
                    cur.execute(f"ALTER TABLE scan_runs ADD COLUMN IF NOT EXISTS {name} TEXT")
                cur.execute("UPDATE jobs SET scope='India',country='India',eligibility=location WHERE source='Remotive' AND lower(location) LIKE '%india%'")
                cur.execute("UPDATE jobs SET scope='India',country='India',eligibility=location WHERE source IN ('Remotive','Himalayas') AND (lower(location) LIKE '%worldwide%' OR lower(location) LIKE '%anywhere%')")
                cur.execute("UPDATE jobs SET scope='International' WHERE source IN ('Remotive','Himalayas') AND scope='India' AND lower(location) NOT LIKE '%india%' AND lower(location) NOT LIKE '%worldwide%' AND lower(location) NOT LIKE '%anywhere%'")
                cur.execute("INSERT INTO profile(id,data) VALUES(1,'{}') ON CONFLICT (id) DO NOTHING")
        return
    with connect(path) as db:
        db.executescript(SCHEMA)
        columns={row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        for name, definition in {
            "scope": "TEXT NOT NULL DEFAULT 'India'", "country": "TEXT", "eligibility": "TEXT",
            "visa_info": "TEXT", "sponsorship": "TEXT", "relocation": "TEXT", "application_deadline": "TEXT",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_scope ON jobs(scope)")
        scan_columns={row["name"] for row in db.execute("PRAGMA table_info(scan_runs)")}
        for name in ("scope", "country"):
            if name not in scan_columns:
                db.execute(f"ALTER TABLE scan_runs ADD COLUMN {name} TEXT")
        db.execute("UPDATE jobs SET scope='India',country='India',eligibility=location WHERE source='Remotive' AND lower(location) LIKE '%india%'")
        db.execute("UPDATE jobs SET scope='India',country='India',eligibility=location WHERE source IN ('Remotive','Himalayas') AND (lower(location) LIKE '%worldwide%' OR lower(location) LIKE '%anywhere%')")
        db.execute("UPDATE jobs SET scope='International' WHERE source IN ('Remotive','Himalayas') AND scope='India' AND lower(location) NOT LIKE '%india%' AND lower(location) NOT LIKE '%worldwide%' AND lower(location) NOT LIKE '%anywhere%'")
        db.execute("INSERT OR IGNORE INTO profile(id,data) VALUES(1,'{}')")


def query(path, sql, args=()):
    with connect(path) as db:
        if is_postgres(path):
            return db.execute(postgres_sql(sql), args).fetchall()
        return db.execute(sql, args).fetchall()


def execute(path, sql, args=()):
    with connect(path) as db:
        if is_postgres(path):
            match=re.match(r"\s*INSERT\s+INTO\s+(jobs|scan_runs|drafts|events|resume_files|login_attempts)\b",sql,re.I)
            statement=postgres_sql(sql)
            if match:
                row=db.execute(statement+" RETURNING id",args).fetchone()
                return row["id"]
            db.execute(statement,args)
            return None
        cur = db.execute(sql, args)
        return cur.lastrowid
