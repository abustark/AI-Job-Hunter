import sqlite3
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
"""


@contextmanager
def connect(path):
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
        return db.execute(sql, args).fetchall()


def execute(path, sql, args=()):
    with connect(path) as db:
        cur = db.execute(sql, args)
        return cur.lastrowid
