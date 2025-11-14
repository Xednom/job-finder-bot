# sources.py
import aiohttp
import feedparser
from typing import List, Dict, Any
import hashlib


async def fetch_jobs_remotive(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 20,
    location: str | None = None,
    remote_only: bool = True,
) -> List[Dict[str, Any]]:
    base = "https://remotive.io/api/remote-jobs"
    params = {"search": query, "limit": str(limit)}
    async with session.get(base, params=params, raise_for_status=True) as resp:
        data = await resp.json()
    jobs = data.get("jobs", [])
    # Normalize and compute unique_id
    normalized = []
    for j in jobs:
        unique = (
            j.get("id")
            or j.get("url")
            or hashlib.md5(
                (j.get("title", "") + j.get("company_name", "")).encode()
            ).hexdigest()
        )
        normalized.append(
            {
                "unique_id": str(unique),
                "title": j.get("title"),
                "company": j.get("company_name"),
                "url": j.get("url"),
                "location": j.get("candidate_required_location") or j.get("location"),
                "raw": j,
            }
        )
    return normalized[:limit]


async def fetch_jobs_remoteok(
    session: aiohttp.ClientSession, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    # RemoteOK provides JSON at https://remoteok.com/api
    # Their API returns first element as metadata; jobs follow.
    async with session.get(
        "https://remoteok.com/api",
        headers={"User-Agent": "JobFinderBot/1.0"},
        raise_for_status=True,
    ) as resp:
        data = await resp.json()
    jobs = []
    for item in data:
        # skip meta objects that aren't job listings
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        title = item.get("position") or item.get("title")
        unique = (
            item.get("id")
            or item.get("url")
            or hashlib.md5((title or "").encode()).hexdigest()
        )
        # quick text match for query (simple)
        if (
            query.lower() in (title or "").lower()
            or query.lower() in (item.get("company", "") or "").lower()
        ):
            jobs.append(
                {
                    "unique_id": str(unique),
                    "title": title,
                    "company": item.get("company"),
                    "url": "https://remoteok.com" + (item.get("url") or ""),
                    "location": item.get("location") or "Remote",
                    "raw": item,
                }
            )
        if len(jobs) >= limit:
            break
    return jobs


async def fetch_jobs_rss(
    session: aiohttp.ClientSession, feed_url: str, limit: int = 20
) -> List[Dict[str, Any]]:
    # feedparser works synchronously; fetch content then parse
    async with session.get(feed_url, raise_for_status=True) as resp:
        text = await resp.text()
    feed = feedparser.parse(text)
    results = []
    for e in feed.entries[:limit]:
        uniq = (
            e.get("id")
            or e.get("link")
            or hashlib.md5(
                (e.get("title", "") + e.get("link", "")).encode()
            ).hexdigest()
        )
        results.append(
            {
                "unique_id": str(uniq),
                "title": e.get("title"),
                "company": e.get("author") or "",
                "url": e.get("link"),
                "location": e.get("location") if "location" in e else None,
                "raw": e,
            }
        )
    return results
