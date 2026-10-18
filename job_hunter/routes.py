import csv
import io
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, session, url_for, send_file
import requests
from werkzeug.utils import secure_filename

from .db import connect, execute, query, is_postgres
from .matching import score
from .sources import SOURCES

bp = Blueprint("main", __name__)
STATUSES = ["Discovered", "To Review", "Saved", "Preparing", "Ready for Review", "Applied", "Interview", "Offer", "Rejected", "Withdrawn", "Dismissed"]
DEFAULT_PROFILE={"skills":[],"roles":["Data Analyst","Python Analyst","Data Scientist","BI Analyst","Reporting Analyst","Analytics","Data Operations"],"locations":["Madurai","Remote","Coimbatore","Chennai"],"enabled_sources":["Remotive","Himalayas"],"greenhouse_boards":[],"lever_boards":[],"international_countries":[]}
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


def db(): return current_app.config["DATABASE"]


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not current_app.config["AUTH_REQUIRED"]:
        return redirect(url_for("main.dashboard"))
    if session.get("owner_authenticated"):
        return redirect(url_for("main.dashboard"))
    next_path=request.args.get("next", "")
    if request.method=="POST":
        next_path=request.form.get("next", "")
        remote_addr=request.remote_addr or "unknown"
        cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec="seconds")
        execute(db(),"DELETE FROM login_attempts WHERE attempted_at<?",(cutoff,))
        recent=query(db(),"SELECT COUNT(*) AS n FROM login_attempts WHERE remote_addr=? AND attempted_at>=?",(remote_addr,cutoff))[0]["n"]
        if recent>=8:
            flash("Too many unsuccessful sign-in attempts. Wait 15 minutes and try again.","error")
        else:
            password=request.form.get("password", "")
            valid=False
            try:
                valid=current_app.config["PASSWORD_CHECK"](current_app.config["OWNER_PASSWORD_HASH"],password)
            except (ValueError,TypeError):
                valid=False
            if valid:
                execute(db(),"DELETE FROM login_attempts WHERE remote_addr=?",(remote_addr,))
                session.clear(); session["owner_authenticated"]=True; session.permanent=True
                if next_path.startswith("/") and not next_path.startswith("//"):
                    return redirect(next_path)
                return redirect(url_for("main.dashboard"))
            execute(db(),"INSERT INTO login_attempts(remote_addr,attempted_at) VALUES(?,?)",(remote_addr,NOW()))
            flash("Invalid password.","error")
    if not (next_path.startswith("/") and not next_path.startswith("//")):
        next_path=""
    return render_template("login.html", next_path=next_path)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have signed out.","success")
    return redirect(url_for("main.login"))


def get_profile():
    row = query(db(), "SELECT data FROM profile WHERE id=1")[0]
    try: data=json.loads(row["data"])
    except (ValueError, TypeError): data={}
    return {**DEFAULT_PROFILE,**data}


def enrich(rows, profile):
    result=[]
    for row in rows:
        item=dict(row); item.update(score(item, profile)); result.append(item)
    return result


@bp.app_context_processor
def global_context(): return {"statuses": STATUSES, "nav_endpoint": request.endpoint, "auth_required": current_app.config["AUTH_REQUIRED"], "authenticated": bool(session.get("owner_authenticated")), "hosted_mode": is_postgres(db())}


@bp.route("/")
def dashboard():
    counts={s: query(db(), "SELECT COUNT(*) AS n FROM jobs WHERE status=?", (s,))[0]["n"] for s in STATUSES}
    jobs=query(db(), "SELECT * FROM jobs WHERE scope='India' AND status NOT IN ('Dismissed','Rejected','Withdrawn') ORDER BY discovered_at DESC LIMIT 100")
    ranked=sorted(enrich(jobs, get_profile()), key=lambda x:(x["score"] or -1), reverse=True)
    scans=query(db(), "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 4")
    return render_template("dashboard.html", counts=counts, jobs=ranked[:5], scans=scans)


@bp.route("/jobs")
def jobs():
    search=request.args.get("q", "").strip(); status=request.args.get("status", ""); source=request.args.get("source", "")
    location=request.args.get("location", "").strip(); work_mode=request.args.get("work_mode", ""); min_score=request.args.get("min_score", "")
    scope=request.args.get("scope", "India")
    sql="SELECT * FROM jobs WHERE 1=1"; args=[]
    if search:
        term=f"%{search}%"; sql+=" AND (title LIKE ? OR company LIKE ? OR description LIKE ? OR skills LIKE ?)"; args.extend([term]*4)
    if status: sql+=" AND status=?"; args.append(status)
    if source: sql+=" AND source=?"; args.append(source)
    if scope in ("India","International"): sql+=" AND scope=?"; args.append(scope)
    if location: sql+=" AND lower(location) LIKE ?"; args.append(f"%{location.lower()}%")
    if work_mode: sql+=" AND work_mode=?"; args.append(work_mode)
    sql+=" ORDER BY discovered_at DESC LIMIT 250"
    rows=query(db(), sql, args)
    order=request.args.get("sort", "match")
    data=enrich(rows, get_profile())
    if min_score.isdigit(): data=[x for x in data if x["score"] is not None and x["score"]>=int(min_score)]
    if order == "newest": data.sort(key=lambda x:x["discovered_at"], reverse=True)
    elif order == "location":
        priorities=[p.lower() for p in get_profile().get("locations",[])]; data.sort(key=lambda x:min((i for i,p in enumerate(priorities) if p in (x.get("location","")+" "+x.get("work_mode","")).lower()),default=len(priorities)))
    else: data.sort(key=lambda x:(x["score"] is not None, x["score"] or 0), reverse=True)
    return render_template("jobs.html", jobs=data, q=search, status=status, source=source, sort=order, location=location, work_mode=work_mode, min_score=min_score, scope=scope, sources=sorted({r["source"] for r in query(db(), "SELECT DISTINCT source FROM jobs")}))


@bp.route("/jobs/add", methods=["GET", "POST"])
def add_job():
    values=request.form if request.method=="POST" else {}
    if request.method=="POST":
        title=values.get("title", "").strip(); company=values.get("company", "").strip(); link=values.get("url", "").strip()
        if not title or not company: flash("Title and company are required.", "error")
        elif link and (urlparse(link).scheme not in ("http", "https") or not urlparse(link).netloc): flash("Use a complete http or https listing URL.", "error")
        elif len(title)>180 or len(company)>180 or len(values.get("description", ""))>30000: flash("One or more fields exceed the allowed length.", "error")
        else:
            now=NOW(); status=values.get("status", "To Review")
            if status not in STATUSES: status="To Review"
            scope=values.get("scope", "India")
            if scope not in ("India","International"): scope="India"
            jid=execute(db(), "INSERT INTO jobs(title,company,url,location,work_mode,source,posted_at,discovered_at,last_seen,salary,description,skills,job_type,seniority,status,notes,follow_up,scope,country,eligibility,visa_info,sponsorship,relocation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (title,company,link,values.get("location", "").strip(),values.get("work_mode", "Unknown"),values.get("source", "Manual")[:80],values.get("posted_at") or None,now,now,values.get("salary") or None,values.get("description", "").strip(),values.get("skills", "").strip(),values.get("job_type") or None,values.get("seniority") or None,status,values.get("notes", "").strip(),values.get("follow_up") or None,scope,values.get("country") or ("India" if scope=="India" else None),values.get("eligibility") or None,values.get("visa_info") or None,values.get("sponsorship") or None,values.get("relocation") or None))
            execute(db(), "INSERT INTO events(job_id,event,created_at) VALUES(?,?,?)", (jid,"Job added",now)); flash("Job added to your workspace.", "success"); return redirect(url_for("main.job_detail", job_id=jid))
    return render_template("add_job.html", values=values)


@bp.route("/jobs/<int:job_id>")
def job_detail(job_id):
    rows=query(db(), "SELECT * FROM jobs WHERE id=?", (job_id,))
    if not rows: return render_template("not_found.html"),404
    job=dict(rows[0]); job.update(score(job,get_profile()))
    drafts=query(db(), "SELECT * FROM drafts WHERE job_id=? ORDER BY id DESC", (job_id,))
    events=query(db(), "SELECT * FROM events WHERE job_id=? ORDER BY id DESC LIMIT 20", (job_id,))
    return render_template("job_detail.html", job=job, drafts=drafts, events=events)


@bp.route("/jobs/<int:job_id>/update", methods=["POST"])
def update_job(job_id):
    rows=query(db(), "SELECT status FROM jobs WHERE id=?", (job_id,))
    if not rows: return render_template("not_found.html"),404
    status=request.form.get("status", rows[0]["status"])
    if status not in STATUSES: flash("Choose a valid status.", "error")
    else:
        execute(db(),"UPDATE jobs SET status=?,notes=?,follow_up=? WHERE id=?",(status,request.form.get("notes", "")[:4000],request.form.get("follow_up") or None,job_id))
        if status != rows[0]["status"]: execute(db(),"INSERT INTO events(job_id,event,created_at) VALUES(?,?,?)",(job_id,f"Status changed to {status}",NOW()))
        flash("Job updated.","success")
    return redirect(url_for("main.job_detail",job_id=job_id))


@bp.route("/jobs/<int:job_id>/draft", methods=["POST"])
def draft(job_id):
    row=query(db(),"SELECT * FROM jobs WHERE id=?",(job_id,))
    if not row: return render_template("not_found.html"),404
    kind=request.form.get("kind", "Cover letter"); content=request.form.get("content", "").strip()
    if kind not in ("Cover letter", "Application answer", "Resume notes"): kind="Cover letter"
    if not content: content=f"Draft for {row[0]['title']} at {row[0]['company']}.\n\nAdd only accurate details from your verified profile. Review and edit before use."
    if len(content)>20000: flash("Draft is too long.","error")
    else:
        now=NOW(); execute(db(),"INSERT INTO drafts(job_id,kind,content,created_at,updated_at) VALUES(?,?,?,?,?)",(job_id,kind,content,now,now))
        execute(db(),"UPDATE jobs SET status='Preparing' WHERE id=? AND status IN ('To Review','Saved','Discovered')",(job_id,)); flash("Editable draft created. Review it before external use.","success")
    return redirect(url_for("main.job_detail",job_id=job_id))


@bp.route("/drafts")
def drafts(): return render_template("drafts.html", drafts=query(db(),"SELECT d.*,j.title,j.company FROM drafts d LEFT JOIN jobs j ON j.id=d.job_id ORDER BY d.id DESC"))


@bp.route("/drafts/<int:draft_id>", methods=["POST"])
def edit_draft(draft_id):
    content=request.form.get("content", "").strip()
    if len(content)>20000: flash("Draft is too long.","error")
    else:
        execute(db(),"UPDATE drafts SET content=?,updated_at=?,reviewed=? WHERE id=?",(content,NOW(),1 if request.form.get("reviewed") else 0,draft_id)); flash("Draft saved.","success")
    return redirect(url_for("main.drafts"))


@bp.route("/profile", methods=["GET","POST"])
def profile():
    data=get_profile()
    if request.method=="POST":
        data.update({"name":request.form.get("name","").strip(),"headline":request.form.get("headline","").strip(),"summary":request.form.get("summary","").strip(),"experience_years":request.form.get("experience_years","3"),"experience_months":request.form.get("experience_months","2"),"skills":[x.strip() for x in request.form.get("skills","").split(",") if x.strip()],"roles":[x.strip() for x in request.form.get("roles","").splitlines() if x.strip()],"locations":[x.strip() for x in request.form.get("locations","Madurai\nRemote\nCoimbatore\nChennai").splitlines() if x.strip()],"international_countries":[x.strip() for x in request.form.get("international_countries","").splitlines() if x.strip() and x.strip().lower()!="india"],"resume_text":request.form.get("resume_text","").strip()})
        if len(data["resume_text"])>50000 or len(data["summary"])>4000: flash("A profile field is too long.","error")
        else: execute(db(),"UPDATE profile SET data=? WHERE id=1",(json.dumps(data),)); flash("Profile saved.","success")
    return render_template("profile.html", profile=data)


@bp.route("/resume/upload", methods=["POST"])
def upload_resume():
    f=request.files.get("resume");
    if not f or not f.filename: flash("Choose a PDF or DOCX file.","error"); return redirect(url_for("main.profile"))
    name=secure_filename(f.filename)
    if Path(name).suffix.lower() not in (".pdf", ".docx"): flash("Only PDF and DOCX files are supported.","error"); return redirect(url_for("main.profile"))
    from io import BytesIO
    file_bytes=f.read()
    if len(file_bytes)>5*1024*1024: flash("Resume files are limited to 5 MB.","error"); return redirect(url_for("main.profile"))
    text=""
    try:
        if Path(name).suffix.lower()==".pdf":
            from pypdf import PdfReader
            text="\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(file_bytes)).pages)
        else:
            from docx import Document
            text="\n".join(p.text for p in Document(BytesIO(file_bytes)).paragraphs)
    except Exception: flash("Resume stored, but text extraction failed. Paste or edit resume text below.","error")
    execute(db(),"INSERT INTO resume_files(filename,content,created_at) VALUES(?,?,?)",(name,file_bytes,NOW()))
    p=get_profile(); p["resume_file"]=name
    if text:
        p["resume_text"]=text[:50000]
    execute(db(),"UPDATE profile SET data=? WHERE id=1",(json.dumps(p),))
    if text: flash("Resume stored securely and extracted for your review.","success")
    return redirect(url_for("main.profile"))


@bp.route("/resume/download")
def download_resume():
    rows=query(db(),"SELECT filename,content FROM resume_files ORDER BY id DESC LIMIT 1")
    if not rows: return render_template("not_found.html"),404
    from io import BytesIO
    return send_file(BytesIO(bytes(rows[0]["content"])),download_name=rows[0]["filename"],as_attachment=True)


@bp.route("/discover", methods=["GET","POST"])
def discover():
    profile_data=get_profile()
    if request.method=="POST":
        source=request.form.get("source", "Remotive"); term=request.form.get("query", "Data Analyst").strip()[:100]
        scope=request.form.get("scope", "India"); country=request.form.get("country", "").strip()
        if scope not in ("India","International"): scope="India"
        if scope=="International" and (not country or country.lower()=="india"):
            flash("Choose a destination country other than India before scanning International Jobs.","error"); return redirect(url_for("main.discover",scope=scope))
        if source not in SOURCES: flash("Unknown provider.","error"); return redirect(url_for("main.discover",scope=scope))
        if scope=="India" and source=="Remotive":
            flash("Remotive is a global remote feed without a dependable India location filter. Use Himalayas or configured company boards for India Jobs.","error"); return redirect(url_for("main.discover",scope=scope))
        if source not in profile_data.get("enabled_sources", list(SOURCES)):
            flash("Enable this source in Settings before scanning it.","error"); return redirect(url_for("main.discover",scope=scope,country=country))
        boards=profile_data.get("greenhouse_boards",[]) if source=="Greenhouse" else profile_data.get("lever_boards",[]) if source=="Lever" else None
        if source in ("Greenhouse","Lever") and not boards:
            flash(f"Add at least one {source} company board token in Settings first.","error"); return redirect(url_for("main.discover",scope=scope,country=country))
        scan_cutoff=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec="seconds")
        recent=query(db(),"SELECT COUNT(*) n FROM scan_runs WHERE source=? AND scope=? AND COALESCE(country,'')=COALESCE(?,'') AND started_at>=? AND outcome IN ('Success','Running')",(source,scope,country or None,scan_cutoff))[0]["n"]
        daily_limit=1 if source=="Himalayas" else 4
        if recent>=daily_limit:
            flash(f"{source} was already scanned {recent} time(s) for this market in the last day. Its public feed updates slowly; try again later.","error")
            return redirect(url_for("main.discover",scope=scope,country=country))
        start=NOW(); run=execute(db(),"INSERT INTO scan_runs(started_at,source,outcome,scope,country) VALUES(?,?,?,?,?)",(start,source,"Running",scope,country or None))
        fetched=added=dupes=0; err=None
        try:
            results=SOURCES[source](term,50 if source in ("Remotive","Greenhouse","Lever") else 20,scope,country or None,boards); fetched=len(results)
            for item in results:
                if not item.get("title") or not item.get("company"): continue
                with connect(db()) as conn:
                    exists=conn.execute("SELECT id FROM jobs WHERE source=? AND source_id=?",(source,item.get("source_id"))).fetchone()
                    if exists: conn.execute("UPDATE jobs SET last_seen=? WHERE id=?",(NOW(),exists["id"])); dupes+=1; continue
                    # URL matching catches provider IDs changing while retaining safe distinct roles.
                    exists=conn.execute("SELECT id FROM jobs WHERE url<>'' AND lower(url)=lower(?)",(item.get("url", ""),)).fetchone()
                    if exists: dupes+=1; continue
                    now=NOW(); conn.execute("INSERT INTO jobs(title,company,url,location,work_mode,source,source_id,posted_at,discovered_at,last_seen,salary,description,skills,job_type,seniority,status,scope,country,eligibility,visa_info,sponsorship,relocation,application_deadline) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'To Review',?,?,?,?,?,?,?)",(item["title"],item["company"],item.get("url",""),item.get("location",""),item.get("work_mode","Unknown"),source,item.get("source_id"),item.get("posted_at"),now,now,item.get("salary"),item.get("description",""),item.get("skills",""),item.get("job_type"),item.get("seniority"),item.get("scope",scope),item.get("country",country),item.get("eligibility"),item.get("visa_info"),item.get("sponsorship"),item.get("relocation"),item.get("application_deadline")))
                    added+=1
            outcome="Success" if not err else "Error"
        except requests.Timeout:
            err=f"{source} did not respond before the 15-second timeout. Check your connection and try again later."
            outcome="Error"
        except requests.ConnectionError:
            err=f"Could not connect to {source}. Check your internet connection and retry the scan."
            outcome="Error"
        except requests.HTTPError as e:
            status=e.response.status_code if e.response is not None else "unknown"
            err=f"{source} returned HTTP {status}. The provider may be temporarily unavailable; try again later."
            outcome="Error"
        except (ValueError, requests.exceptions.JSONDecodeError):
            err=f"{source} returned an unreadable response. Try again later."
            outcome="Error"
        except sqlite3.ProgrammingError as e:
            detail=" ".join(str(e).split())[:180]
            err=f"Could not save {source} results to the local database: {detail}"
            outcome="Error"
        except Exception as e:
            current_app.logger.exception("Unexpected %s scan failure", source)
            if type(e).__module__.startswith("psycopg"):
                err=f"Could not save {source} results to the hosted database. Check the deployment logs."
            else:
                detail=" ".join(str(e).split())[:180]
                error_type=f"{type(e).__module__}.{type(e).__name__}"
                err=f"{source} scan failed unexpectedly ({error_type})"+(f": {detail}" if detail else ". See the application log for details.")
            outcome="Error"
        execute(db(),"UPDATE scan_runs SET finished_at=?,outcome=?,fetched=?,added=?,duplicates=?,error=? WHERE id=?",(NOW(),outcome,fetched,added,dupes,err,run))
        flash(f"{source}: fetched {fetched}, added {added}, duplicates refreshed/skipped {dupes}."+(f" {err}" if err else ""),"error" if err else "success")
        return redirect(url_for("main.jobs",scope=scope))
    scope=request.args.get("scope","India")
    if scope not in ("India","International"): scope="India"
    country=request.args.get("country", "")
    enabled=profile_data.get("enabled_sources",list(SOURCES))
    available=(["Himalayas","Greenhouse","Lever"] if scope=="India" else ["Himalayas","Remotive","Greenhouse","Lever"])
    sources=[s for s in available if s in enabled]
    scans=query(db(),"SELECT * FROM scan_runs WHERE scope=? ORDER BY id DESC LIMIT 10",(scope,))
    return render_template("discover.html", sources=sources, scans=scans, scope=scope,country=country,countries=profile_data.get("international_countries",[]),greenhouse_configured=bool(profile_data.get("greenhouse_boards")),lever_configured=bool(profile_data.get("lever_boards")))


@bp.route("/export.csv")
def export_csv():
    rows=query(db(),"SELECT title,company,url,location,work_mode,source,posted_at,salary,description,skills,job_type,seniority,status,notes,follow_up,discovered_at FROM jobs ORDER BY id")
    stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(rows[0].keys() if rows else ["title","company","url","location","work_mode","source","posted_at","salary","description","skills","job_type","seniority","status","notes","follow_up","discovered_at"])
    for row in rows: writer.writerow([("'"+str(v) if str(v).startswith(("=","+","-","@")) else v) for v in row])
    response=make_response(stream.getvalue()); response.headers["Content-Type"]="text/csv; charset=utf-8"; response.headers["Content-Disposition"]="attachment; filename=job-hunter-export.csv"; return response


@bp.route("/import", methods=["GET","POST"])
def import_csv():
    if request.method=="POST":
        upload=request.files.get("file"); confirm=request.form.get("confirm")
        try:
            if confirm:
                token=session.pop("import_preview", "")
                preview=query(db(),"SELECT content,expires_at FROM import_previews WHERE token=?",(token,)) if token else []
                if not preview or preview[0]["expires_at"]<NOW(): raise ValueError("The import preview expired. Upload the file again.")
                rows=json.loads(preview[0]["content"]); execute(db(),"DELETE FROM import_previews WHERE token=?",(token,))
            else:
                if not upload or not upload.filename.lower().endswith(".csv"): flash("Choose a CSV file.","error"); return redirect(url_for("main.import_csv"))
                rows=list(csv.DictReader(io.TextIOWrapper(upload.stream,encoding="utf-8-sig")))
            if len(rows)>1000: raise ValueError("Import is limited to 1,000 rows at a time.")
            if not confirm:
                token=secrets.token_urlsafe(18)
                execute(db(),"DELETE FROM import_previews WHERE expires_at<?",(NOW(),))
                execute(db(),"INSERT INTO import_previews(token,content,expires_at) VALUES(?,?,?)",(token,json.dumps(rows,ensure_ascii=False),(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(timespec="seconds")))
                session["import_preview"]=token
                return render_template("import.html", preview=rows[:10], total=len(rows), uploaded=True, error=None)
            count=0
            for i,row in enumerate(rows,2):
                title=(row.get("title") or "").strip(); company=(row.get("company") or "").strip(); link=(row.get("url") or "").strip()
                if not title or not company: raise ValueError(f"Row {i}: title and company are required.")
                if link and urlparse(link).scheme not in ("http","https"): raise ValueError(f"Row {i}: URL must start with http or https.")
                if link and query(db(),"SELECT id FROM jobs WHERE lower(url)=lower(?)",(link,)): continue
                now=NOW(); execute(db(),"INSERT INTO jobs(title,company,url,location,work_mode,source,posted_at,discovered_at,last_seen,salary,description,skills,status,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(title,company,link,row.get("location", ""),row.get("work_mode","Unknown"),row.get("source","CSV Import"),row.get("posted_at") or None,now,now,row.get("salary") or None,row.get("description",""),row.get("skills",""),row.get("status") if row.get("status") in STATUSES else "To Review",row.get("notes",""))); count+=1
            flash(f"Imported {count} jobs; duplicate URLs were skipped.","success"); return redirect(url_for("main.jobs"))
        except (ValueError,UnicodeError,csv.Error) as exc: flash(str(exc),"error")
    return render_template("import.html", preview=None,total=0,uploaded=False,error=None)


@bp.route("/pipeline")
def pipeline():
    rows=query(db(),"SELECT * FROM jobs WHERE status IN ('Preparing','Ready for Review','Applied','Interview','Offer','Rejected','Withdrawn') ORDER BY status,discovered_at DESC")
    return render_template("pipeline.html", jobs=rows)


@bp.route("/settings", methods=["GET","POST"])
def settings():
    if request.method=="POST":
        data=get_profile(); data["enabled_sources"]=[s for s in SOURCES if s in request.form.getlist("sources")]
        data["greenhouse_boards"]=[x.strip() for x in request.form.get("greenhouse_boards","").splitlines() if re.fullmatch(r"[A-Za-z0-9_-]{1,80}",x.strip())][:10]
        data["lever_boards"]=[x.strip() for x in request.form.get("lever_boards","").splitlines() if re.fullmatch(r"[A-Za-z0-9_-]{1,80}",x.strip())][:10]
        execute(db(),"UPDATE profile SET data=? WHERE id=1",(json.dumps(data),)); flash("Source preferences saved.","success")
    profile_data=get_profile()
    return render_template("settings.html", ai_configured=bool(__import__('os').getenv("GEMINI_API_KEY")), scans=query(db(),"SELECT * FROM scan_runs ORDER BY id DESC LIMIT 10"), enabled_sources=profile_data.get("enabled_sources",list(SOURCES)), sources=SOURCES, greenhouse_boards=profile_data.get("greenhouse_boards",[]), lever_boards=profile_data.get("lever_boards",[]))


@bp.route("/backup.json")
def backup():
    data={"jobs":[dict(x) for x in query(db(),"SELECT * FROM jobs")],"profile":get_profile(),"drafts":[dict(x) for x in query(db(),"SELECT * FROM drafts")],"exported_at":NOW()}
    r=make_response(json.dumps(data,ensure_ascii=False,indent=2)); r.headers["Content-Type"]="application/json"; r.headers["Content-Disposition"]="attachment; filename=job-hunter-backup.json"; return r
