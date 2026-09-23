from typing import Any, Dict, List
import html

import requests
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("FunTools")


def fetch_json(url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def get_weather(latitude: float, longitude: float) -> Dict[str, Any]:
    """Get current conditions and today's rain chance for coordinates."""
    data = fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "precipitation_probability_max,precipitation_sum,weather_code",
            "forecast_days": 1,
            "timezone": "auto",
        },
    )
    daily = data.get("daily", {})
    return {
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "current": data.get("current", {}),
        "current_units": data.get("current_units", {}),
        "today": {
            "rain_probability_percent": (daily.get("precipitation_probability_max") or [None])[0],
            "precipitation_sum_mm": (daily.get("precipitation_sum") or [None])[0],
            "weather_code": (daily.get("weather_code") or [None])[0],
        },
    }


@mcp.tool()
def book_recs(topic: str, limit: int = 5) -> Dict[str, Any]:
    """Get up to five Open Library book recommendations for a topic."""
    limit = max(1, min(limit, 5))
    data = fetch_json(
        "https://openlibrary.org/search.json",
        {"q": topic, "limit": limit, "fields": "title,author_name,first_publish_year,key"},
    )
    picks: List[Dict[str, Any]] = []
    for book in data.get("docs", [])[:limit]:
        work = book.get("key")
        picks.append(
            {
                "title": book.get("title", "Unknown title"),
                "author": (book.get("author_name") or ["Unknown"])[0],
                "year": book.get("first_publish_year"),
                "url": f"https://openlibrary.org{work}" if work else None,
            }
        )
    return {"topic": topic, "results": picks}


@mcp.tool()
def random_joke() -> Dict[str, Any]:
    """Get a safe one-line joke."""
    data = fetch_json(
        "https://v2.jokeapi.dev/joke/Any",
        {"type": "single", "safe-mode": "", "blacklistFlags": "nsfw,religious,political,racist,sexist,explicit"},
    )
    return {"joke": data.get("joke", "No joke found")}


@mcp.tool()
def random_dog() -> Dict[str, Any]:
    """Get a random dog image URL."""
    data = fetch_json("https://dog.ceo/api/breeds/image/random")
    return {"url": data.get("message"), "status": data.get("status")}


@mcp.tool()
def trivia() -> Dict[str, Any]:
    """Get one multiple-choice trivia question and its answer."""
    results = fetch_json(
        "https://opentdb.com/api.php",
        {"amount": 1, "type": "multiple"},
    ).get("results", [])
    if not results:
        return {"error": "No trivia question available"}
    question = results[0]
    return {
        "question": html.unescape(question["question"]),
        "correct_answer": html.unescape(question["correct_answer"]),
        "incorrect_answers": [html.unescape(answer) for answer in question["incorrect_answers"]],
    }


if __name__ == "__main__":
    mcp.run()
