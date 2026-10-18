from datetime import datetime, timezone
from html import unescape
import re
import time
import requests
from urllib.parse import quote


def plain(html):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", html or ""))).strip()


def _text_values(value):
    """Normalize provider strings or structured arrays into display-safe text."""
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for item in values:
        if isinstance(item, dict):
            item = item.get("name") or item.get("alpha2") or item.get("slug")
        if isinstance(item, (str, int, float)) and str(item).strip():
            out.append(str(item).strip())
    return out


def _text_field(value, default=""):
    """Convert provider fields to SQLite-safe text without storing Python containers."""
    if value is None:
        return default
    if isinstance(value, (list, tuple, dict)):
        return ", ".join(_text_values(value)) or default
    return str(value)


def _get_with_connection_retry(url, *, params, timeout=15):
    """Retry a GET once when the connection fails before a response arrives."""
    for attempt in range(2):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout):
            if attempt:
                raise
            time.sleep(1)


def fetch_remotive(query, limit=50, scope="International", country=None, boards=None):
    r = _get_with_connection_retry("https://remotive.com/api/remote-jobs", params={"search": query, "limit": min(limit, 100)})
    r.raise_for_status()
    data = r.json()
    out = []
    for x in data.get("jobs", []):
        eligible=x.get("candidate_required_location", "")
        if scope == "India" and not re.search(r"\b(india|worldwide|anywhere|everywhere)\b", eligible, re.I):
            continue
        if scope == "International" and country and country.lower() not in eligible.lower() and not re.search(r"\b(worldwide|anywhere|everywhere)\b", eligible, re.I):
            continue
        out.append(dict(title=x.get("title", ""), company=x.get("company_name", ""), url=x.get("url", ""),
            location=eligible or "Remote; eligibility not specified", country=country if scope == "International" else "India",
            eligibility=eligible or "Not specified", scope=scope, work_mode="Remote",
            source="Remotive", source_id=str(x.get("id", "")), posted_at=x.get("publication_date"),
            salary=x.get("salary") or None, description=plain(x.get("description")), skills=x.get("category", ""),
            job_type=x.get("job_type"), seniority=None))
    return out


def fetch_himalayas(query, limit=20, scope="India", country=None, boards=None):
    geo="India" if scope == "India" else country
    params={"q": query, "sort": "recent", "page": 1}
    if geo: params["country"]=geo
    r = requests.get("https://himalayas.app/jobs/api/search", params=params, timeout=15)
    r.raise_for_status()
    out = []
    for x in r.json().get("jobs", [])[:min(limit, 20)]:
        link = _text_field(x.get("applicationLink") or x.get("guid"))
        desc = plain(_text_field(x.get("description") or x.get("excerpt", "")))
        salary = None
        if x.get("minSalary") or x.get("maxSalary"):
            salary = f"{x.get('currency') or ''} {x.get('minSalary') or ''}–{x.get('maxSalary') or ''} {x.get('salaryPeriod') or ''}".strip()
        restrictions=_text_values(x.get("locationRestrictions"))
        location=", ".join(restrictions) if restrictions else "Worldwide (per source)"
        pub_date=x.get("pubDate")
        if isinstance(pub_date, (int, float)):
            timestamp=pub_date / 1000 if pub_date > 100_000_000_000 else pub_date
            pub_date=datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        elif pub_date is not None:
            pub_date=_text_field(pub_date)
        eligibility=", ".join(restrictions) if restrictions else "Worldwide (per source)"
        seniority=", ".join(_text_values(x.get("seniority"))) or None
        employment_type=", ".join(_text_values(x.get("employmentType"))) or None
        title=_text_field(x.get("title"))
        company=_text_field(x.get("companyName"))
        source_id=_text_field(x.get("guid") or link or f"{_text_field(x.get('companySlug'))}:{title}")
        out.append(dict(title=title, company=company, url=link,
            location=location, country=geo, eligibility=eligibility, scope=scope, work_mode="Remote",
            source="Himalayas", source_id=source_id,
            posted_at=pub_date, salary=salary, description=desc,
            skills=", ".join(_text_values(x.get("categories"))), job_type=employment_type, seniority=seniority))
    return out


def _country_matches(location, country):
    if not country:
        return False
    aliases={"india": ("india", "bengaluru", "bangalore", "chennai", "madurai", "coimbatore", "hyderabad", "pune", "mumbai", "noida", "gurugram", "gurgaon", "delhi", "kolkata"),
        "united states": ("united states", "usa", "u.s.", "new york", "california", "texas")}
    candidates=aliases.get(country.lower(), (country.lower(),))
    return any(term in (location or "").lower() for term in candidates)


def _job_matches_query(item, query):
    terms=[t.lower() for t in re.findall(r"[\w+.-]+", query) if len(t)>2]
    hay=(item.get("title", "")+" "+item.get("description", "")+" "+item.get("skills", "")).lower()
    return not terms or any(term in hay for term in terms)


def fetch_greenhouse(query, limit=50, scope="India", country=None, boards=None):
    if not boards: return []
    out=[]
    for board in boards[:10]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", board): continue
        r=requests.get(f"https://boards-api.greenhouse.io/v1/boards/{quote(board,safe='')}/jobs",params={"content":"true"},timeout=15)
        r.raise_for_status()
        for x in r.json().get("jobs",[])[:limit]:
            office=x.get("location") or {}; location=office.get("name","") if isinstance(office,dict) else str(office)
            if not _job_matches_query({"title":x.get("title", ""),"description":plain((x.get("content") or ""))},query): continue
            is_india=_country_matches(location,"India")
            if scope=="India" and not is_india: continue
            if scope=="International" and (is_india or not _country_matches(location,country)): continue
            out.append(dict(title=x.get("title",""),company=x.get("company_name") or board,url=x.get("absolute_url", ""),
                location=location,work_mode="Unknown",source="Greenhouse",source_id=f"{board}:{x.get('id')}",
                posted_at=x.get("updated_at"),salary=None,description=plain(x.get("content", "")),skills="",job_type=None,seniority=None,
                scope=scope,country=country or ("India" if is_india else None),eligibility="Not specified"))
    return out


def fetch_lever(query, limit=50, scope="India", country=None, boards=None):
    if not boards: return []
    out=[]
    for board in boards[:10]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", board): continue
        r=requests.get(f"https://api.lever.co/v0/postings/{quote(board,safe='')}",params={"mode":"json","limit":limit},timeout=15)
        r.raise_for_status()
        for x in r.json()[:limit]:
            categories=x.get("categories") or {}; location=categories.get("allLocations") or categories.get("location") or ""
            if isinstance(location,list): location=", ".join(location)
            loc_country=(x.get("country") or "").upper(); is_india=loc_country=="IN" or _country_matches(location,"India")
            if not _job_matches_query({"title":x.get("text", ""),"description":plain(x.get("descriptionPlain") or x.get("description",""))},query): continue
            if scope=="India" and not is_india: continue
            if scope=="International" and (is_india or not (loc_country.lower()==(country or "").lower() or _country_matches(location,country))): continue
            out.append(dict(title=x.get("text",""),company=board,url=x.get("hostedUrl", ""),location=location,
                work_mode=(x.get("workplaceType") or "Unknown").title(),source="Lever",source_id=f"{board}:{x.get('id')}",
                posted_at=x.get("createdAt"),salary=x.get("salaryDescriptionPlain") or None,
                description=plain(x.get("descriptionPlain") or x.get("description","")),skills="",job_type=categories.get("commitment"),seniority=categories.get("level"),
                scope=scope,country=country or ("India" if is_india else loc_country),eligibility="Not specified"))
    return out


SOURCES = {"Remotive": fetch_remotive, "Himalayas": fetch_himalayas, "Greenhouse": fetch_greenhouse, "Lever": fetch_lever}
