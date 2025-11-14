# sources.py
import aiohttp
import feedparser
from typing import List, Dict, Any
import hashlib
import re
from html import unescape


async def fetch_jobs_remotive(
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 20,
    location: str | None = None,
    remote_only: bool = True,
) -> List[Dict[str, Any]]:
    base = "https://remotive.io/api/remote-jobs"
    # Clean the query - remove extra quotes and spaces
    clean_query = query.strip().strip('"').strip("'")
    params = {"search": clean_query, "limit": str(limit)}
    
    try:
        async with session.get(
            base, 
            params=params, 
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "JobFinderBot/1.0"}
        ) as resp:
            # Don't raise for status yet, handle errors gracefully
            if resp.status == 526:
                # Cloudflare error - API might be rate limiting
                return []
            resp.raise_for_status()
            data = await resp.json()
    except aiohttp.ClientError as e:
        print(f"Error fetching from Remotive: {e}")
        return []
    
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


async def fetch_jobs_onlinejobs(
    session: aiohttp.ClientSession, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """Fetch jobs from OnlineJobs.ph"""
    base_url = "https://www.onlinejobs.ph/jobseekers/jobsearch"
    params = {
        "jobkeyword": query,
        "fullTime": "on",
        "partTime": "on",
        "Freelance": "on"
    }
    
    try:
        async with session.get(
            base_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        ) as resp:
            if resp.status != 200:
                print(f"OnlineJobs.ph returned status {resp.status}")
                return []
            html = await resp.text()
    except aiohttp.ClientError as e:
        print(f"Error fetching from OnlineJobs.ph: {e}")
        return []
    
    jobs = []
    
    # Parse HTML to extract job listings
    # OnlineJobs.ph uses div elements with class "jobpost-cat-box" for each job
    
    # Find all job listings using regex patterns
    # Pattern to match job title and link
    job_pattern = re.compile(
        r'<div class="jobpost-cat-box.*?">.*?'
        r'<a href="(/jobseekers/jobdetails/\d+)".*?>'
        r'<h3.*?>(.*?)</h3>',
        re.DOTALL | re.IGNORECASE
    )
    
    # Pattern to match company name
    company_pattern = re.compile(
        r'<p class="vam".*?>(.*?)</p>',
        re.DOTALL | re.IGNORECASE
    )
    
    matches = job_pattern.finditer(html)
    
    for match in matches:
        if len(jobs) >= limit:
            break
            
        job_url_path = match.group(1)
        job_title = unescape(match.group(2).strip())
        
        # Clean up title - remove HTML tags
        job_title = re.sub(r'<[^>]+>', '', job_title).strip()
        
        # Try to find company name in the section following the title
        section_start = match.end()
        section = html[section_start:section_start + 500]
        company_match = company_pattern.search(section)
        company_name = ""
        if company_match:
            company_name = unescape(company_match.group(1).strip())
            company_name = re.sub(r'<[^>]+>', '', company_name).strip()
        
        full_url = f"https://www.onlinejobs.ph{job_url_path}"
        
        # Generate unique ID
        unique_id = hashlib.md5(full_url.encode()).hexdigest()
        
        jobs.append({
            "unique_id": unique_id,
            "title": job_title,
            "company": company_name or "OnlineJobs.ph Employer",
            "url": full_url,
            "location": "Philippines (Remote)",
            "raw": {
                "source": "onlinejobs.ph",
                "title": job_title,
                "company": company_name,
                "url": full_url
            }
        })
    
    return jobs

