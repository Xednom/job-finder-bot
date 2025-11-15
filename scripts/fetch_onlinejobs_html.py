#!/usr/bin/env python3
"""Fetch OnlineJobs.ph search page and print short HTML snippet for debugging."""
import asyncio
from urllib.parse import urlencode
import aiohttp

async def fetch(query: str):
    base_url = "https://www.onlinejobs.ph/jobseekers/jobsearch"
    params = {"jobkeyword": query, "fullTime": "on", "partTime": "on", "Freelance": "on"}
    url = base_url + "?" + urlencode(params)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            print('status', resp.status)
            html = await resp.text()
            print('len', len(html))
            print(html[:1000])

if __name__ == '__main__':
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else 'virtual assistant'
    asyncio.run(fetch(q))
