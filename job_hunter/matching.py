import re
from datetime import datetime, timezone

DEFAULT_LOCATIONS = ["Madurai", "Remote", "Coimbatore", "Chennai"]


def score(job, profile):
    title = (job.get("title") or "").lower()
    text = " ".join(str(job.get(k) or "") for k in ("title", "description", "skills")).lower()
    roles = profile.get("roles") or ["data analyst", "data scientist", "bi analyst", "reporting analyst", "python analyst", "analytics"]
    role_hit = any(r.lower().strip() in title for r in roles if r.strip())
    skills = [s.lower().strip() for s in profile.get("skills", []) if s.strip()]
    matched = [s for s in skills if re.search(r"\b" + re.escape(s) + r"\b", text)]
    locations = profile.get("locations") or DEFAULT_LOCATIONS
    loc = (job.get("location") or "").lower()
    mode = (job.get("work_mode") or "").lower()
    location_hit = next((i for i, item in enumerate(locations) if item.lower() in (loc + " " + mode)), None)
    components, reasons = [], []
    components.append((30, 1 if role_hit else 0, "role"))
    if skills:
        components.append((25, len(matched) / len(skills), "skills"))
    if job.get("location") or job.get("work_mode"):
        components.append((20, (len(locations) - location_hit) / len(locations) if location_hit is not None else 0.15, "location"))
    posted = job.get("posted_at")
    if posted:
        try:
            dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            age = max(0, (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else datetime.now(timezone.utc) - dt).days)
            components.append((10, max(0, 1 - age / 30), "freshness"))
        except ValueError:
            pass
    total = sum(weight for weight, _, _ in components)
    value = round(100 * sum(weight * part for weight, part, _ in components) / total) if total else None
    if role_hit: reasons.append("Target role appears in the title.")
    if matched: reasons.append("Profile skills found: " + ", ".join(matched[:6]) + ".")
    if location_hit is not None: reasons.append(f"Location preference #{location_hit + 1}: {locations[location_hit]}.")
    if not role_hit: reasons.append("Role match is uncertain; inspect the listing.")
    return {"score": value, "reasons": reasons, "matched_skills": matched, "missing_skills": [s for s in skills if s not in matched], "confidence": "Limited" if len(components) < 3 else "Standard"}
