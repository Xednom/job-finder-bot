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


async def fetch_jobs_weworkremotely(
    session: aiohttp.ClientSession, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """Fetch jobs from We Work Remotely"""
    base_url = "https://weworkremotely.com/remote-jobs/search"
    params = {"term": query}
    
    try:
        async with session.get(
            base_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        ) as resp:
            if resp.status != 200:
                print(f"WeWorkRemotely returned status {resp.status}")
                return []
            html = await resp.text()
    except (aiohttp.ClientError, TimeoutError, Exception) as e:
        print(f"Error fetching from WeWorkRemotely: {e}")
        return []
    
    jobs = []
    
    # Pattern to match job listings
    job_pattern = re.compile(
        r'<li class="feature">.*?<a href="(/remote-jobs/[^"]+)".*?'
        r'<span class="title">(.*?)</span>.*?'
        r'<span class="company">(.*?)</span>',
        re.DOTALL | re.IGNORECASE
    )
    
    matches = job_pattern.finditer(html)
    
    for match in matches:
        if len(jobs) >= limit:
            break
            
        job_url_path = match.group(1)
        job_title = unescape(match.group(2).strip())
        company_name = unescape(match.group(3).strip())
        
        # Clean up - remove HTML tags
        job_title = re.sub(r'<[^>]+>', '', job_title).strip()
        company_name = re.sub(r'<[^>]+>', '', company_name).strip()
        
        full_url = f"https://weworkremotely.com{job_url_path}"
        unique_id = hashlib.md5(full_url.encode()).hexdigest()
        
    jobs.append({
            "unique_id": unique_id,
            "title": job_title,
            "company": company_name or "WeWorkRemotely Employer",
            "url": full_url,
            "location": "Remote",
            "raw": {
                "source": "weworkremotely.com",
                "title": job_title,
                "company": company_name,
                "url": full_url
            }
        })
    
    return jobs


async def fetch_jobs_flexjobs(
    session: aiohttp.ClientSession, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """Fetch jobs from FlexJobs (limited free access)"""
    # Note: FlexJobs has limited free access, using their job search
    base_url = "https://www.flexjobs.com/search"
    params = {"search": query, "location": "Anywhere"}
    
    try:
        async with session.get(
            base_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        ) as resp:
            if resp.status != 200:
                print(f"FlexJobs returned status {resp.status}")
                return []
            html = await resp.text()
    except (aiohttp.ClientError, TimeoutError, Exception) as e:
        print(f"Error fetching from FlexJobs: {e}")
        return []
    
    jobs = []
    
    # Pattern for FlexJobs listings
    job_pattern = re.compile(
        r'<h5[^>]*>.*?<a href="([^"]+/jobs/[^"]+)"[^>]*>(.*?)</a>.*?</h5>.*?'
        r'<h6[^>]*>(.*?)</h6>',
        re.DOTALL | re.IGNORECASE
    )
    
    matches = job_pattern.finditer(html)
    
    for match in matches:
        if len(jobs) >= limit:
            break
            
        job_url = match.group(1)
        job_title = unescape(match.group(2).strip())
        company_name = unescape(match.group(3).strip())
        
        # Clean up
        job_title = re.sub(r'<[^>]+>', '', job_title).strip()
        company_name = re.sub(r'<[^>]+>', '', company_name).strip()
        
        if not job_url.startswith('http'):
            full_url = f"https://www.flexjobs.com{job_url}"
        else:
            full_url = job_url
            
        unique_id = hashlib.md5(full_url.encode()).hexdigest()

        jobs.append({
            "unique_id": unique_id,
            "title": job_title,
            "company": company_name or "FlexJobs Employer",
            "url": full_url,
            "location": "Remote/Flexible",
            "raw": {
                "source": "flexjobs.com",
                "title": job_title,
                "company": company_name,
                "url": full_url,
            },
        })
    
    return jobs


async def fetch_jobs_jobstreet(
    session: aiohttp.ClientSession, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """Fetch jobs from JobStreet Philippines"""
    base_url = "https://www.jobstreet.com.ph/jobs"
    params = {"keywords": query, "work-type": "remote"}
    
    try:
        async with session.get(
            base_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        ) as resp:
            if resp.status != 200:
                print(f"JobStreet returned status {resp.status}")
                return []
            html = await resp.text()
    except (aiohttp.ClientError, TimeoutError, Exception) as e:
        print(f"Error fetching from JobStreet: {e}")
        return []
    
    jobs = []
    
    # JobStreet uses JSON data in script tags, try to extract
    json_pattern = re.compile(
        r'window\.SEEK_REDUX_DATA\s*=\s*({.*?});',
        re.DOTALL,
    )

    json_match = json_pattern.search(html)
    if json_match:
        try:
            import json

            data = json.loads(json_match.group(1))
            job_list = data.get('results', {}).get('results', {}).get('jobs', [])

            for job in job_list[:limit]:
                job_id = job.get('id', '')
                job_title = job.get('title', 'Untitled')
                company_name = job.get('companyName', '')
                location = job.get('location', 'Philippines')

                full_url = f"https://www.jobstreet.com.ph/job/{job_id}"
                unique_id = hashlib.md5(full_url.encode()).hexdigest()

                jobs.append(
                    {
                        "unique_id": unique_id,
                        "title": job_title,
                        "company": company_name or "JobStreet Employer",
                        "url": full_url,
                        "location": location,
                        "raw": {
                            "source": "jobstreet.com.ph",
                            "title": job_title,
                            "company": company_name,
                            "url": full_url,
                        },
                    }
                )
        except Exception as e:
            print(f"Error parsing JobStreet JSON: {e}")
    
    return jobs


async def fetch_jobs_upwork(
    session: aiohttp.ClientSession, query: str, limit: int = 20, contractor_tier: int = 1
) -> List[Dict[str, Any]]:
    """Fetch jobs from Upwork
    
    Args:
        contractor_tier: Experience level (1=Entry Level, 2=Intermediate, 3=Expert)
    """
    search_url = "https://www.upwork.com/nx/search/jobs/"
    search_params = {
        "q": query,
        "sort": "recency",
        "contractor_tier": str(contractor_tier)  # 1=Entry, 2=Intermediate, 3=Expert
    }
    
    jobs = []
    
    # Map contractor_tier to experience level name
    if contractor_tier == 1:
        experience_level = "Entry Level"
    elif contractor_tier == 2:
        experience_level = "Intermediate"
    else:  # contractor_tier == 3
        experience_level = "Expert"
    
    # Fetch from Upwork search page with more realistic browser headers
    try:
        async with session.get(
            search_url,
            params=search_params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
        ) as resp:
            if resp.status == 403:
                print("Upwork blocking request (403). This source may not work reliably due to bot detection.")
                return []
            if resp.status != 200:
                print(f"Upwork search returned status {resp.status}")
                return []
            html = await resp.text()
            
            # Try to extract job data from the page
            # Upwork often embeds JSON data in script tags
            json_pattern = re.compile(
                r'data-initial-state="({.*?})"',
                re.DOTALL
            )
            
            json_match = json_pattern.search(html)
            if json_match:
                try:
                    import json
                    # Unescape HTML entities
                    json_str = unescape(json_match.group(1))
                    data = json.loads(json_str)
                    
                    # Navigate the data structure to find jobs
                    # This structure may vary, so we'll be defensive
                    job_list = []
                    if isinstance(data, dict):
                        # Try to find job listings in various possible locations
                        for key in ['jobs', 'results', 'searchResults']:
                            if key in data:
                                job_list = data[key] if isinstance(data[key], list) else []
                                break
                    
                    for job in job_list[:limit]:
                        if not isinstance(job, dict):
                            continue
                            
                        job_id = job.get('id', '') or job.get('ciphertext', '')
                        job_title = job.get('title', 'Untitled')
                        budget = job.get('amount', {}).get('amount', '') if 'amount' in job else ''
                        
                        # Skip if no valid job ID or title
                        if not job_id or not job_title:
                            continue
                        
                        # Build job URL
                        full_url = f"https://www.upwork.com/jobs/{job_id}"
                        unique_id = hashlib.md5(full_url.encode()).hexdigest()
                        
                        jobs.append({
                            "unique_id": unique_id,
                            "title": job_title,
                            "company": "Upwork Client",
                            "url": full_url,
                            "location": "Remote (Freelance)",
                            "experience": experience_level,
                            "salary": str(budget) if budget else "",
                            "raw": {
                                "source": "upwork.com",
                                "title": job_title,
                                "url": full_url,
                                "budget": budget,
                                "contractor_tier": contractor_tier
                            }
                        })
                        
                except Exception as e:
                    print(f"Error parsing Upwork JSON: {e}")
                    
    except (aiohttp.ClientError, TimeoutError, Exception) as e:
        print(f"Error fetching from Upwork search page: {e}")
    
    return jobs[:limit]


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
    session: aiohttp.ClientSession,
    query: str,
    limit: int = 20,
    full_time: bool = True,
    part_time: bool = True,
    freelance: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch jobs from OnlineJobs.ph.

    The function builds the search URL using the `jobkeyword` parameter and
    includes employment type flags as query parameters matching the
    example URL:

        https://www.onlinejobs.ph/jobseekers/jobsearch?jobkeyword=virtual+assistant&fullTime=on&partTime=on&Freelance=on

    Args:
        full_time: include fullTime=on when True
        part_time: include partTime=on when True
        freelance: include Freelance=on when True
    """
    base_url = "https://www.onlinejobs.ph/jobseekers/jobsearch"
    # Build params to match the example URL and allow selective employment types
    params = {"jobkeyword": query}
    if full_time:
        params["fullTime"] = "on"
    if part_time:
        params["partTime"] = "on"
    if freelance:
        params["Freelance"] = "on"
    
    try:
        async with session.get(
            base_url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=60),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        ) as resp:
            if resp.status != 200:
                print(f"OnlineJobs.ph returned status {resp.status}")
                return []
            html = await resp.text()
    except (aiohttp.ClientError, TimeoutError, Exception) as e:
        print(f"Error fetching from OnlineJobs.ph (timeout or connection issue): {e}")
        return []
    
    jobs = []
    
    # Parse HTML to extract job listings
    # OnlineJobs.ph uses div elements with class "jobpost-cat-box" for each job
    
    # Find all job listings using regex patterns
    # Two possible markup patterns are used by OnlineJobs.ph.
    # 1) Older pattern: div.jobpost-cat-box contains an <a href="/jobseekers/jobdetails/<id>">
    job_pattern_old = re.compile(
        r'<div class="jobpost-cat-box.*?">.*?'
        r'<a href="(/jobseekers/jobdetails/\d+)".*?>'
        r'<h3.*?>(.*?)</h3>',
        re.DOTALL | re.IGNORECASE,
    )

    # 2) Newer pattern: an <a href="/jobseekers/job/<slug>-<id>"> wraps the div.jobpost-cat-box
    outer_pattern = re.compile(
        r'<a[^>]*href="(/jobseekers/job/[^"]+)"[^>]*>\s*'
        r'<div[^>]*class="[^\"]*jobpost-cat-box[^\"]*"[^>]*>(.*?)</div>\s*</a>',
        re.DOTALL | re.IGNORECASE,
    )
    
    # Pattern to match company name
    company_pattern = re.compile(
        r'<p class="vam".*?>(.*?)</p>',
        re.DOTALL | re.IGNORECASE
    )
    
    # Try the old pattern first, then fallback to the anchor wrapping pattern
    matches = list(job_pattern_old.finditer(html))
    use_outer = False
    if not matches:
        outer_matches = list(outer_pattern.finditer(html))
        if outer_matches:
            # convert outer matches into a format similar to job_pattern_old
            # group 1 -> url/path, group 2 -> inner html (we'll extract title and company later)
            matches = outer_matches
            use_outer = True
    
    for match in matches:
        if len(jobs) >= limit:
            break

        if not use_outer:
            # old style: group(1)=path to job details, group(2)=title
            job_url_path = match.group(1)
            job_title = unescape(match.group(2).strip())
            # company may be in the following HTML section; search nearby
            company_section = html[match.end(): match.end() + 500]
            company_match = company_pattern.search(company_section)
            company_name = (
                unescape(company_match.group(1).strip()) if company_match else ""
            )
        else:
            # outer pattern: group(1)=path, group(2)=inner HTML that contains the title and company
            job_url_path = match.group(1)
            inner_html = match.group(2)
            # title in h3 or h4
            title_match = re.search(r'<h[34][^>]*>(.*?)</h[34]>', inner_html, re.DOTALL | re.IGNORECASE)
            job_title = unescape(title_match.group(1).strip()) if title_match else "Untitled"
            # company in a <p> before <em>
            company_match = re.search(r'<p[^>]*>\s*(.*?)\s*<em', inner_html, re.DOTALL | re.IGNORECASE)
            company_name = (
                unescape(company_match.group(1).strip()) if company_match else ""
            )

        # Clean up title - remove HTML tags
        job_title = re.sub(r'<[^>]+>', '', job_title).strip()

        # company_name is captured by regex (cleaned below), keep fallback pattern
        if not company_name:
            section_start = match.end()
            section = html[section_start:section_start + 500]
            company_match = company_pattern.search(section)
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

