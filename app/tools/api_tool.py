"""
External API fetch tool.

Supported services: weather, finance, news.
Each service maps to a clean adapter that normalises the response.
"""

from __future__ import annotations

import os
from typing import Any

import requests


def fetch_api(service: str, params: dict[str, Any]) -> dict:
    """
    Fetch data from a supported external API.

    Args:
        service: One of "weather", "finance", "news".
        params:  Service-specific parameters (see adapters below).

    Returns:
        Normalised dict with the fetched data.
    """
    adapters = {
        "weather": _fetch_weather,
        "finance": _fetch_finance,
        "news": _fetch_news,
    }

    if service not in adapters:
        raise ValueError(f"Unknown service '{service}'. Supported: {list(adapters)}")

    return adapters[service](params)


def _fetch_weather(params: dict) -> dict:
    """
    Fetch weather for a city.
    params: {"city": "San Francisco", "days": 3}
    Requires: OPENWEATHER_API_KEY
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        raise OSError("OPENWEATHER_API_KEY not set in .env")

    city = params.get("city", "")
    # Geocode
    geo_resp = requests.get(
        "https://api.openweathermap.org/geo/1.0/direct",
        params={"q": city, "limit": 1, "appid": api_key},
        timeout=10,
    )
    geo_resp.raise_for_status()
    geo = geo_resp.json()
    if not geo:
        raise ValueError(f"City not found: {city}")

    lat, lon = geo[0]["lat"], geo[0]["lon"]

    # Forecast
    forecast_resp = requests.get(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "metric",
            "cnt": params.get("days", 3) * 8,
        },
        timeout=10,
    )
    forecast_resp.raise_for_status()
    data = forecast_resp.json()

    days = {}
    for item in data["list"]:
        date = item["dt_txt"][:10]
        if date not in days:
            days[date] = {
                "date": date,
                "temp_min": 999,
                "temp_max": -999,
                "conditions": [],
            }
        t = item["main"]["temp"]
        days[date]["temp_min"] = min(days[date]["temp_min"], t)
        days[date]["temp_max"] = max(days[date]["temp_max"], t)
        days[date]["conditions"].append(item["weather"][0]["description"])

    return {"city": city, "forecast": list(days.values())}


def _fetch_finance(params: dict) -> dict:
    """
    Fetch stock price or company financials.
    params: {"ticker": "AAPL", "metric": "price"}
    Requires: ALPHAVANTAGE_API_KEY
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        raise OSError("ALPHAVANTAGE_API_KEY not set in .env")

    ticker = params.get("ticker", "")
    resp = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("Global Quote", {})

    return {
        "ticker": ticker,
        "price": data.get("05. price"),
        "change_pct": data.get("10. change percent"),
        "volume": data.get("06. volume"),
        "latest_trading_day": data.get("07. latest trading day"),
    }


def _fetch_news(params: dict) -> dict:
    """
    Fetch recent news headlines.
    params: {"query": "supply chain disruption", "num_articles": 5}
    Requires: NEWSAPI_KEY
    """
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        raise OSError("NEWSAPI_KEY not set in .env")

    resp = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": params.get("query", ""),
            "pageSize": params.get("num_articles", 5),
            "sortBy": "publishedAt",
            "apiKey": api_key,
        },
        timeout=10,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])

    return {
        "query": params.get("query"),
        "articles": [
            {
                "title": a["title"],
                "source": a["source"]["name"],
                "published": a["publishedAt"],
                "url": a["url"],
                "summary": a.get("description", ""),
            }
            for a in articles
        ],
    }
