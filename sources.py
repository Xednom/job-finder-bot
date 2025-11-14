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
                "url": full_url
            }
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
        re.DOTALL
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
                
                jobs.append({
                    "unique_id": unique_id,
                    "title": job_title,
                    "company": company_name or "JobStreet Employer",
                    "url": full_url,
                    "location": location,
                    "raw": {
                        "source": "jobstreet.com.ph",
                        "title": job_title,
                        "company": company_name,
                        "url": full_url
                    }
                })
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
    # Try RSS feed first (has more structured data)
    rss_url = "https://www.upwork.com/ab/feed/jobs/rss"
    rss_params = {"q": query, "sort": "recency"}
    
    # Also try the main search page as fallback
    search_url = "https://www.upwork.com/nx/search/jobs/"
    search_params = {
        "q": query,
        "sort": "recency",
        "contractor_tier": str(contractor_tier)  # 1=Entry, 2=Intermediate, 3=Expert
    }
    
    jobs = []
    
    # Try RSS feed first
    try:
        async with session.get(
            rss_url,
            params=rss_params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        ) as resp:
            if resp.status == 200:
                text = await resp.text()
                feed = feedparser.parse(text)
                
                for entry in feed.entries[:limit]:
                    job_title = entry.get('title', 'Untitled')
                    job_url = entry.get('link', '')
                    description = entry.get('summary', '')
                    
                    # Extract budget/rate from description if available
                    budget_match = re.search(r'<b>Budget</b>:\s*([^<]+)', description)
                    hourly_match = re.search(r'<b>Hourly Range</b>:\s*([^<]+)', description)
                    
                    budget = ""
                    if budget_match:
                        budget = budget_match.group(1).strip()
                    elif hourly_match:
                        budget = hourly_match.group(1).strip()
                    
                    # Extract skills
                    skills_match = re.search(r'<b>Skills</b>:\s*([^<]+)', description)
                    skills = skills_match.group(1).strip() if skills_match else ""
                    
                    unique_id = hashlib.md5(job_url.encode()).hexdigest()
                    
                    # Map contractor_tier to experience level name
                    if contractor_tier == 1:
                        experience_level = "Entry Level"
                    elif contractor_tier == 2:
                        experience_level = "Intermediate"
                    else:  # contractor_tier == 3
                        experience_level = "Expert"
                    
                    jobs.append({
                        "unique_id": unique_id,
                        "title": job_title,
                        "company": "Upwork Client",
                        "url": job_url,
                        "location": "Remote (Freelance)",
                        "experience": experience_level,
                        "salary": budget,
                        "description": skills[:200] if skills else "",
                        "raw": {
                            "source": "upwork.com",
                            "title": job_title,
                            "url": job_url,
                            "budget": budget,
                            "skills": skills,
                            "contractor_tier": contractor_tier
                        }
                    })
                    
                if jobs:
                    return jobs[:limit]
    except (aiohttp.ClientError, TimeoutError, Exception) as e:
        print(f"Error fetching from Upwork RSS: {e}")
    
    # Fallback: Try scraping the search page
    try:
        async with session.get(
            search_url,
            params=search_params,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        ) as resp:
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
                        
                        # Build job URL
                        if job_id:
                            full_url = f"https://www.upwork.com/jobs/{job_id}"
                        else:
                            continue
                        
                        unique_id = hashlib.md5(full_url.encode()).hexdigest()
                        
                        # Map contractor_tier to experience level name
                        if contractor_tier == 1:
                            experience_level = "Entry Level"
                        elif contractor_tier == 2:
                            experience_level = "Intermediate"
                        else:  # contractor_tier == 3
                            experience_level = "Expert"
                        
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

