import asyncio
import json
import random
import re
import sys
from contextlib import AsyncExitStack
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ollama import chat


MODEL = "gemma4:e2b"
MAX_STEPS = 4


def coordinates_from_text(text: str):
    named = re.search(
        r"(-?\d+(?:\.\d+)?)\s*°?\s*([NS]).*?(-?\d+(?:\.\d+)?)\s*°?\s*([EW])",
        text,
        re.IGNORECASE,
    )
    pair = named or re.search(
        r"(-?\d+(?:\.\d+)?)\s*(?:°|lat(?:itude)?)?\s*,\s*(-?\d+(?:\.\d+)?)\s*(?:°|lon(?:gitude)?)?",
        text,
        re.IGNORECASE,
    )
    if not pair:
        return None
    latitude, longitude = float(pair.group(1)), float(pair.group(3) if named else pair.group(2))
    if named:
        latitude *= -1 if pair.group(2).upper() == "S" else 1
        longitude *= -1 if pair.group(4).upper() == "W" else 1
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return latitude, longitude
    return None


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def tool_result(result) -> str:
    if getattr(result, "isError", False):
        return json.dumps({"error": "Tool call failed"})
    parts = [item.text for item in result.content if getattr(item, "type", "") == "text"]
    return "\n".join(parts) if parts else result.model_dump_json()


def llm_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    response = chat(model=MODEL, messages=messages, format="json", options={"temperature": 0})
    return json.loads(response.message.content)


def requested_action(user: str):
    text = user.lower()
    if "book_recs" in text and any(word in text for word in ("what", "about", "does", "help")):
        return {"action": "final", "answer": "book_recs searches Open Library for book recommendations by topic and returns titles, authors, and links."}
    if any(word in text for word in ("weather", "rain", "temperature", "forecast")):
        coordinates = coordinates_from_text(user)
        if coordinates:
            return {"action": "get_weather", "args": {"latitude": coordinates[0], "longitude": coordinates[1]}}
        return {"action": "final", "answer": "Please share latitude and longitude for the weather report."}
    if "trivia" in text or "quiz question" in text:
        return {"action": "trivia", "args": {}}
    if "joke" in text:
        return {"action": "random_joke", "args": {}}
    if "dog" in text and any(word in text for word in ("photo", "picture", "pic", "image")):
        return {"action": "random_dog", "args": {}}
    if "book" in text or "read" in text:
        topic = re.search(r"(?:about|on|for)\s+(.+?)(?:[?.!]|$)", user, re.IGNORECASE)
        return {"action": "book_recs", "args": {"topic": topic.group(1) if topic else "weekend reading", "limit": 3}}
    return None


def answer_from_tool(name: str, payload: Dict[str, Any]) -> str:
    if "error" in payload:
        return f"I could not fetch that right now: {payload['error']}"
    if name == "get_weather":
        current, units, today = payload["current"], payload["current_units"], payload["today"]
        temperature = current.get("temperature_2m")
        unit = units.get("temperature_2m", "°C")
        rain = today.get("rain_probability_percent")
        wind = current.get("wind_speed_10m")
        wind_unit = units.get("wind_speed_10m", "km/h")
        rain_text = "Rain chance is unavailable" if rain is None else f"Rain chance today: {rain}%"
        return f"Now: {temperature}{unit}, wind {wind} {wind_unit}. {rain_text}."
    if name == "book_recs":
        books = payload.get("results", [])
        if not books:
            return "I could not find matching books."
        return "Book ideas: " + "; ".join(
            f"{book['title']} — {book['author']} ({book['url']})" for book in books
        )
    if name == "random_joke":
        return payload.get("joke", "No joke found")
    if name == "random_dog":
        return f"Dog photo: {payload.get('url')}"
    return ""


def reflect(draft: str, observations: List[str]) -> str:
    messages = [
        {
            "role": "system",
            "content": "Return JSON only. Use {\"status\":\"confirm\",\"answer\":\"\"} when the draft is grounded in the observations. Use {\"status\":\"change\",\"answer\":\"...\"} only to correct wording; never change facts, numbers, titles, or URLs.",
        },
        {"role": "user", "content": json.dumps({"draft": draft, "observations": observations})},
    ]
    try:
        review = llm_json(messages)
        if review.get("status") == "change" and review.get("answer"):
            print("[Reflection: corrected]")
            return review["answer"]
    except (json.JSONDecodeError, KeyError):
        pass
    print("[Reflection: confirmed]")
    return draft


async def main():
    server = StdioServerParameters(command=sys.executable, args=["server_fun.py"])
    async with AsyncExitStack() as stack:
        read_stream, write_stream = await stack.enter_async_context(stdio_client(server))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        tools = (await session.list_tools()).tools
        tool_index = {tool.name: tool for tool in tools}
        tool_context = "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)
        print("Connected tools:", list(tool_index))

        system = (
            "You are Weekend Wizard. Return JSON only. Use {\"action\":\"tool_name\",\"args\":{}} to call a tool or {\"action\":\"final\",\"answer\":\"...\"} to finish. Do not claim a tool is unavailable when it appears below.\n"
            f"Available tools:\n{tool_context}"
        )
        history = [{"role": "system", "content": system}]
        active_trivia = None

        while True:
            user = input("\nYou: ").strip()
            if not user or user.lower() in {"exit", "quit"}:
                return

            if active_trivia and not any(word in user.lower() for word in ("trivia", "question", "quiz")):
                correct = active_trivia["correct_answer"]
                if normalise(user) == normalise(correct):
                    print("\nAgent: Correct! " + correct + " is the right answer.")
                else:
                    print("\nAgent: Not quite. The correct answer is " + correct + ".")
                active_trivia = None
                continue

            history.append({"role": "user", "content": user})
            observations: List[str] = []
            decision = requested_action(user)

            for _ in range(MAX_STEPS):
                if decision is None:
                    try:
                        decision = llm_json(history)
                    except (json.JSONDecodeError, KeyError):
                        decision = {"action": "final", "answer": "I can help with weather, books, jokes, dog photos, or trivia."}

                if decision.get("action") == "final":
                    draft = decision.get("answer", "")
                    print("\nAgent:", reflect(draft, observations))
                    history.append({"role": "assistant", "content": draft})
                    break

                name, args = decision.get("action"), decision.get("args", {})
                if name not in tool_index:
                    decision = {"action": "final", "answer": "I can help with weather, books, jokes, dog photos, or trivia."}
                    continue

                try:
                    payload_text = tool_result(await session.call_tool(name, args))
                    payload = json.loads(payload_text)
                except Exception as exc:
                    payload = {"error": str(exc)}
                observation = json.dumps({"tool": name, "result": payload})
                observations.append(observation)
                history.append({"role": "user", "content": "Observation: " + observation})

                if name == "trivia" and "error" not in payload:
                    active_trivia = payload
                    choices = payload["incorrect_answers"] + [payload["correct_answer"]]
                    random.shuffle(choices)
                    draft = payload["question"] + "\nChoices: " + ", ".join(choices)
                else:
                    draft = answer_from_tool(name, payload)
                decision = {"action": "final", "answer": draft}


if __name__ == "__main__":
    asyncio.run(main())
