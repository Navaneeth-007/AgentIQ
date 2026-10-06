"""
Web search tool — Tavily API with graceful fallback to SerpAPI.

Design: Tavily returns clean, LLM-ready snippets (vs. raw HTML from SerpAPI).
We normalise both responses into the same schema so the agent doesn't care
which backend is active.
"""

from __future__ import annotations

import os
from typing import Any


def run_web_search(query: str, num_results: int = 5) -> dict[str, Any]:
    """
    Search the web and return a list of results with title, url, and snippet.

    Args:
        query:       The search query string.
        num_results: Max number of results to return (1-10).

    Returns:
        {"results": [{"title": ..., "url": ..., "snippet": ...}], "query": query}
    """
    num_results = max(1, min(num_results, 10))

    tavily_key = os.getenv("TAVILY_API_KEY")
    serp_key = os.getenv("SERPAPI_KEY")

    if tavily_key:
        return _tavily_search(query, num_results, tavily_key)
    elif serp_key:
        return _serp_search(query, num_results, serp_key)
    else:
        raise OSError(
            "No search API key found. Set TAVILY_API_KEY or SERPAPI_KEY in .env"
        )


def _tavily_search(query: str, num_results: int, api_key: str) -> dict:
    try:
        from tavily import TavilyClient
    except ImportError:
        raise ImportError("tavily-python not installed. Run: pip install tavily-python")

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=num_results, search_depth="basic")

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in response.get("results", [])
    ]
    return {"results": results, "query": query}


def _serp_search(query: str, num_results: int, api_key: str) -> dict:
    import requests

    resp = requests.get(
        "https://serpapi.com/search",
        params={"q": query, "num": num_results, "api_key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("link", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in data.get("organic_results", [])[:num_results]
    ]
    return {"results": results, "query": query}
