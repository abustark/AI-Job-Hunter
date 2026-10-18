import json
import io
import sqlite3

import pytest
import requests
from werkzeug.security import generate_password_hash

from job_hunter import create_app
from job_hunter.db import init_db, query, postgres_sql
from job_hunter.matching import score
from job_hunter.sources import _get_with_connection_retry, fetch_himalayas, fetch_remotive
from job_hunter.routes import SOURCES as ROUTE_SOURCES


@pytest.fixture
def app(tmp_path):
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"DATABASE":str(tmp_path/"test.sqlite3"),"SECRET_KEY":"test-only"})
    return app


def test_app_starts_and_dashboard_renders(app):
    response=app.test_client().get("/")
    assert response.status_code==200
    assert b"Review queue" in response.data


def test_hosted_dashboard_requires_owner_login(tmp_path):
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"DATABASE":str(tmp_path/"hosted.sqlite3"),"SECRET_KEY":"test-only","AUTH_REQUIRED":True,"OWNER_PASSWORD_HASH":generate_password_hash("correct horse battery staple")})
    client=app.test_client()
    assert client.get("/").status_code==302
    assert client.get("/backup.json").status_code==302
    assert client.get("/resume/download").status_code==302
    assert client.post("/jobs/add",data={"title":"Analyst","company":"Acme"}).status_code==302
    response=client.post("/login",data={"password":"incorrect"},follow_redirects=True)
    assert b"Invalid password" in response.data
    response=client.post("/login",data={"password":"correct horse battery staple"},follow_redirects=True)
    assert response.status_code==200 and b"Review queue" in response.data
    client.post("/logout")
    assert client.get("/profile").status_code==302


def test_login_session_cookie_is_secure_for_https(tmp_path):
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":True,"DATABASE":str(tmp_path/"secure-cookie.sqlite3"),"SECRET_KEY":"test-only","AUTH_REQUIRED":True,"OWNER_PASSWORD_HASH":generate_password_hash("correct horse battery staple"),"SESSION_COOKIE_SECURE":True})
    response=app.test_client().get("/login",base_url="https://jobs.example.test")
    assert response.status_code==200
    assert "Secure" in response.headers["Set-Cookie"] and "HttpOnly" in response.headers["Set-Cookie"]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


def test_production_requires_durable_database_and_owner_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OWNER_PASSWORD_HASH", raising=False)
    with pytest.raises(RuntimeError,match="DATABASE_URL"):
        create_app({"TESTING":False,"INSTANCE_PATH":str(tmp_path)})


def test_discover_separates_india_and_international_scopes(app):
    client=app.test_client()
    india=client.get("/discover")
    international=client.get("/discover?scope=International&country=United%20States")
    assert b"India Jobs" in india.data and b"Search in India" in india.data
    assert b"International Jobs" in international.data and b"United States" in international.data
    assert b'name="scope" value="International"' in international.data
    assert b"Remotive" in international.data


def test_jobs_default_to_india_and_keep_international_results_separate(app):
    client=app.test_client()
    client.post("/jobs/add",data={"title":"India Analyst","company":"Local Co","scope":"India"})
    client.post("/jobs/add",data={"title":"US Analyst","company":"Global Co","scope":"International","country":"United States"})
    india=client.get("/jobs")
    global_jobs=client.get("/jobs?scope=International")
    assert b"India Analyst" in india.data and b"US Analyst" not in india.data
    assert b"US Analyst" in global_jobs.data and b"India Analyst" not in global_jobs.data


def test_settings_exposes_company_board_fields(app):
    response=app.test_client().get("/settings")
    assert response.status_code==200
    assert b"Greenhouse board tokens" in response.data and b"Lever site names" in response.data


def test_database_initialization_is_repeatable(tmp_path):
    path=tmp_path/"repeat.sqlite3"
    init_db(str(path)); init_db(str(path))
    assert query(str(path),"SELECT COUNT(*) n FROM profile")[0]["n"]==1


def test_postgres_sql_adapter_translates_supported_sql():
    assert postgres_sql("SELECT * FROM jobs WHERE id=?") == "SELECT * FROM jobs WHERE id=%s"
    assert postgres_sql("INSERT OR IGNORE INTO profile(id,data) VALUES(1,'{}')").endswith("ON CONFLICT (id) DO NOTHING")


def test_resume_upload_is_persisted_in_database(app):
    client=app.test_client()
    response=client.post("/resume/upload",data={"resume":(io.BytesIO(b"not a real pdf"),"resume.pdf")},content_type="multipart/form-data",follow_redirects=True)
    assert response.status_code==200
    stored=query(app.config["DATABASE"],"SELECT filename,content FROM resume_files")[0]
    assert stored["filename"]=="resume.pdf" and bytes(stored["content"])==b"not a real pdf"


def test_manual_job_is_added_and_can_be_updated(app):
    client=app.test_client()
    response=client.post("/jobs/add",data={"title":"Data Analyst","company":"Example","url":"https://example.com/role","location":"Madurai","work_mode":"On-site","status":"To Review"},follow_redirects=True)
    assert response.status_code==200
    assert b"Example" in response.data
    assert client.get("/jobs?q=Data+Analyst").status_code==200
    row=query(app.config["DATABASE"],"SELECT id FROM jobs")[0]
    client.post(f"/jobs/{row['id']}/update",data={"status":"Applied","notes":"Submitted by owner"})
    assert query(app.config["DATABASE"],"SELECT status FROM jobs WHERE id=?",(row["id"],))[0]["status"]=="Applied"


def test_required_fields_and_invalid_status_are_rejected(app):
    client=app.test_client()
    response=client.post("/jobs/add",data={"title":"","company":"Example"},follow_redirects=True)
    assert b"Title and company are required" in response.data
    client.post("/jobs/add",data={"title":"A","company":"B","url":"javascript:alert(1)"},follow_redirects=True)
    assert query(app.config["DATABASE"],"SELECT COUNT(*) n FROM jobs")[0]["n"]==0


def test_scoring_explains_matches_and_missing_skills():
    result=score({"title":"Data Analyst","location":"Madurai","work_mode":"On-site","skills":"SQL, Excel","posted_at":None},{"roles":["Data Analyst"],"skills":["SQL","Python"],"locations":["Madurai","Remote"]})
    assert result["score"] is not None
    assert result["matched_skills"]==["sql"]
    assert result["missing_skills"]==["python"]
    assert any("Madurai" in reason for reason in result["reasons"])


def test_application_is_not_marked_applied_by_opening_listing(app):
    client=app.test_client()
    client.post("/jobs/add",data={"title":"Data Analyst","company":"Example","url":"https://example.com"})
    job=query(app.config["DATABASE"],"SELECT * FROM jobs")[0]
    client.get(f"/jobs/{job['id']}")
    assert query(app.config["DATABASE"],"SELECT status FROM jobs WHERE id=?",(job["id"],))[0]["status"]=="To Review"


def test_csv_export_escapes_formula_values(app):
    client=app.test_client()
    client.post("/jobs/add",data={"title":"=1+1","company":"Example"})
    text=client.get("/export.csv").data.decode("utf-8")
    assert "'=1+1" in text


def test_remotive_adapter_parses_response(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"jobs":[{"id":42,"title":"Analyst","company_name":"Acme","url":"https://remotive.com/job/42","description":"<p>SQL</p>","publication_date":"2026-10-18","candidate_required_location":"India","job_type":"full_time"}]}
    monkeypatch.setattr("job_hunter.sources.requests.get",lambda *a,**kw:Response())
    item=fetch_remotive("Analyst")[0]
    assert item["source_id"]=="42" and item["work_mode"]=="Remote" and item["description"]=="SQL"


def test_source_get_retries_one_connection_failure(monkeypatch):
    calls=[]
    class Response: pass
    def get(*args, **kwargs):
        calls.append(1)
        if len(calls)==1: raise requests.ConnectionError("temporary")
        return Response()
    monkeypatch.setattr("job_hunter.sources.requests.get",get)
    monkeypatch.setattr("job_hunter.sources.time.sleep",lambda seconds: None)
    assert _get_with_connection_retry("https://example.test",params={}) is not None
    assert len(calls)==2


def test_himalayas_adapter_parses_and_preserves_eligibility(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"jobs":[{"guid":"https://himalayas.app/jobs/1","applicationLink":"https://himalayas.app/jobs/1","title":"Analyst","companyName":"Acme","locationRestrictions":["India"],"pubDate":1792281600,"description":"<b>Python</b>","employmentType":"Full Time","seniority":["Entry-level","Mid-level"]}]}
    monkeypatch.setattr("job_hunter.sources.requests.get",lambda *a,**kw:Response())
    item=fetch_himalayas("Analyst")[0]
    assert item["source_id"].endswith("/1") and "India" in item["location"] and "T" in item["posted_at"]
    assert item["seniority"]=="Entry-level, Mid-level"


def test_himalayas_normalizes_documented_location_restriction_objects(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"jobs":[{"guid":"job-2","title":"Analyst","companyName":"Acme","locationRestrictions":[{"alpha2":"IN","name":"India","slug":"india"}],"seniority":[]}]}
    monkeypatch.setattr("job_hunter.sources.requests.get",lambda *a,**kw:Response())
    item=fetch_himalayas("Analyst")[0]
    assert item["location"]=="India" and item["eligibility"]=="India"


def test_himalayas_normalizes_provider_container_values_before_database_binding(app, monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"jobs":[{"guid":["job-4"],"title":["Analyst"],"companyName":{"name":"Acme"},"applicationLink":["https://example.test/jobs/4"],"locationRestrictions":["India"],"pubDate":["2026-10-18"],"description":["SQL analyst"]}]}
    monkeypatch.setattr("job_hunter.sources.requests.get",lambda *a,**kw:Response())
    response=app.test_client().post("/discover",data={"source":"Himalayas","query":"Analyst","scope":"India"},follow_redirects=True)
    assert response.status_code==200
    assert b"Himalayas: fetched 1, added 1" in response.data
    row=query(app.config["DATABASE"],"SELECT title,company,url,posted_at FROM jobs WHERE source_id='job-4'")[0]
    assert tuple(row)==("Analyst","Acme","https://example.test/jobs/4","2026-10-18")


def test_himalayas_discovery_persists_seniority_array_as_text(app, monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"jobs":[{"guid":"job-3","title":"Analyst","companyName":"Acme","locationRestrictions":["India"],"employmentType":"Full Time","seniority":["Entry-level","Mid-level"],"categories":["Data"]}]}
    monkeypatch.setattr("job_hunter.sources.requests.get",lambda *a,**kw:Response())
    response=app.test_client().post("/discover",data={"source":"Himalayas","query":"Analyst","scope":"India"},follow_redirects=True)
    assert b"Himalayas: fetched 1, added 1" in response.data
    assert query(app.config["DATABASE"],"SELECT seniority FROM jobs WHERE source_id='job-3'")[0]["seniority"]=="Entry-level, Mid-level"


def test_status_history_and_json_backup(app):
    client=app.test_client()
    client.post("/jobs/add",data={"title":"Analyst","company":"Acme"})
    jid=query(app.config["DATABASE"],"SELECT id FROM jobs")[0]["id"]
    client.post(f"/jobs/{jid}/update",data={"status":"Saved"})
    assert query(app.config["DATABASE"],"SELECT COUNT(*) n FROM events WHERE job_id=?",(jid,))[0]["n"]==2
    data=json.loads(client.get("/backup.json").data)
    assert data["jobs"][0]["title"]=="Analyst"


def test_csv_import_requires_preview_then_confirmation(app):
    client=app.test_client()
    payload=("title,company,url,location,work_mode,source\nAnalyst,Acme,https://acme.example/jobs/1,India,Remote,CSV\n").encode()
    preview=client.post("/import",data={"file":(io.BytesIO(payload),"jobs.csv")},content_type="multipart/form-data")
    assert preview.status_code==200 and b"Confirm import" in preview.data
    assert query(app.config["DATABASE"],"SELECT COUNT(*) n FROM jobs")[0]["n"]==0
    result=client.post("/import",data={"confirm":"yes"},follow_redirects=True)
    assert result.status_code==200
    assert query(app.config["DATABASE"],"SELECT COUNT(*) n FROM jobs")[0]["n"]==1


def test_state_changes_require_csrf_token(tmp_path):
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":True,"DATABASE":str(tmp_path/"csrf.sqlite3"),"SECRET_KEY":"csrf-test"})
    response=app.test_client().post("/jobs/add",data={"title":"Analyst","company":"Acme"})
    assert response.status_code==400


def test_discovery_explains_temporary_source_connection_failure(app, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("network details are intentionally not shown")
    monkeypatch.setitem(ROUTE_SOURCES, "Remotive", unavailable)
    client=app.test_client()
    response=client.post("/discover",data={"source":"Remotive","query":"Analyst","scope":"International","country":"United States"},follow_redirects=True)
    assert response.status_code==200
    assert b"Could not connect to Remotive" in response.data
    assert b"network details are intentionally not shown" not in response.data


def test_discovery_exposes_safe_database_binding_cause(app, monkeypatch):
    def bad_record(*args, **kwargs):
        raise sqlite3.ProgrammingError("Error binding parameter 16: type 'list' is not supported")
    monkeypatch.setitem(ROUTE_SOURCES, "Himalayas", bad_record)
    response=app.test_client().post("/discover",data={"source":"Himalayas","query":"Analyst","scope":"India"},follow_redirects=True)
    assert b"Could not save Himalayas results" in response.data
    assert b"Error binding parameter 16" in response.data
