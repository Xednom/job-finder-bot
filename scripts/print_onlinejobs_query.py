#!/usr/bin/env python3
"""Print the constructed OnlineJobs.ph search URL for quick testing.

Usage:
    python3 scripts/print_onlinejobs_query.py "virtual assistant" --types all
    python3 scripts/print_onlinejobs_query.py "data entry" --types fulltime
"""

import sys
from urllib.parse import urlencode


def build_onlinejobs_url(query: str, types: str = "all") -> str:
    base = "https://www.onlinejobs.ph/jobseekers/jobsearch"
    params = {"jobkeyword": query}
    types = (types or "all").lower()
    if types == "all":
        params.update({"fullTime": "on", "partTime": "on", "Freelance": "on"})
    elif types == "fulltime":
        params.update({"fullTime": "on"})
    elif types == "parttime":
        params.update({"partTime": "on"})
    elif types == "freelance":
        params.update({"Freelance": "on"})
    else:
        raise ValueError("Unknown types: choose all|fulltime|parttime|freelance")

    return base + "?" + urlencode(params)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/print_onlinejobs_query.py <query> [--types <all|fulltime|parttime|freelance>]")
        sys.exit(1)
    query = sys.argv[1]
    types = "all"
    if "--types" in sys.argv:
        try:
            types = sys.argv[sys.argv.index("--types") + 1]
        except IndexError:
            print("--types requires a value")
            sys.exit(2)

    print(build_onlinejobs_url(query, types))
