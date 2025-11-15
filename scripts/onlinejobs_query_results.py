#!/usr/bin/env python3
"""Query OnlineJobs.ph using the bot's fetcher and print results.

Usage:
    python3 scripts/onlinejobs_query_results.py "virtual assistant" --types all
"""
import argparse
import asyncio
 

import aiohttp

# Avoid importing the package's fetcher directly to keep this script
# independent (and to allow debugging parsing without importing the bot code)
import re
import hashlib
from urllib.parse import urlencode


async def run(query: str, types: str = "all", limit: int = 10):
    full_time = part_time = freelance = True
    types = (types or "all").lower()
    if types == "fulltime":
        full_time, part_time, freelance = True, False, False
    elif types == "parttime":
        full_time, part_time, freelance = False, True, False
    elif types == "freelance":
        full_time, part_time, freelance = False, False, True

    async with aiohttp.ClientSession() as session:
        # Fetch the search page and parse job posts using a robust regex
        # (We avoid calling the main fetcher to make this script function
        # even when the core bot module is having issues.)
        jobs = []
        base_url = "https://www.onlinejobs.ph/jobseekers/jobsearch"
        params = {"jobkeyword": query}
        if full_time:
            params["fullTime"] = "on"
        if part_time:
            params["partTime"] = "on"
        if freelance:
            params["Freelance"] = "on"
        url = base_url + "?" + urlencode(params)
        headers = {"User-Agent": "Mozilla/5.0"}

        async with session.get(url, headers=headers) as resp:
            html = await resp.text()

        # Robust approach: find anchor wrapping the job div, then parse inner HTML
        outer = re.compile(
            r'<a[^>]*href="(/jobseekers/job/[^"]+)"[^>]*>\s*'
            r'<div[^>]*class="[^\\"]*jobpost-cat-box[^\\"]*"[^>]*>(.*?)</div>\s*</a>',
            re.DOTALL | re.IGNORECASE,
        )
        for path, inner in outer.findall(html)[:limit]:
            # Extract title
            tmatch = re.search(r'<h[34][^>]*>(.*?)</h[34]>', inner, re.DOTALL | re.IGNORECASE)
            title = re.sub(r'<[^>]+>', '', tmatch.group(1)).strip() if tmatch else "Untitled"

            # Extract company from <p> tag preceding <em>
            cmatch = re.search(r'<p[^>]*>\s*(.*?)\s*<em', inner, re.DOTALL | re.IGNORECASE)
            company = re.sub(r'<[^>]+>', '', cmatch.group(1)).strip() if cmatch else ""

            full_url = f"https://www.onlinejobs.ph{path}"
            jobs.append(
                {
                    "unique_id": hashlib.md5(full_url.encode()).hexdigest(),
                    "title": title,
                    "company": company,
                    "url": full_url,
                    "location": "Philippines (Remote)",
                    "raw": {"source": "onlinejobs.ph"},
                }
            )

    print(f"Found {len(jobs)} jobs for '{query}' (types={types}, limit={limit})")
    for i, job in enumerate(jobs, start=1):
        title = job.get("title")
        company = job.get("company")
        url = job.get("url")
        location = job.get("location")
        print(f"[{i}] {title} — {company} — {location}\n    {url}\n")


def main():
    parser = argparse.ArgumentParser(description="Query OnlineJobs.ph and print parsed job results")
    parser.add_argument("query", help="Search keywords (e.g. 'virtual assistant')")
    parser.add_argument("--types", default="all", choices=["all", "fulltime", "parttime", "freelance"], help="Employment types to include")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to fetch")
    args = parser.parse_args()
    asyncio.run(run(args.query, types=args.types, limit=args.limit))


if __name__ == "__main__":
    main()
