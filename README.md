# Weekend Wizard

Weekend Wizard is a local CLI agent that uses Ollama and MCP tools to provide weather, book ideas, jokes, dog photo links, and trivia.

## Requirements

- Python 3.10 or later
- Ollama

## Setup

From the `weekend-wizard` folder, create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install "mcp>=1.2,<2" requests ollama
```

Download the configured local model:

```powershell
ollama pull gemma4:e2b
```

## Run

```powershell
.\.venv\Scripts\python.exe agent_fun.py
```

The agent starts `server_fun.py` automatically as its MCP tools server.

Type a request at the `You:` prompt. Type `exit` or `quit` to close the application.

## Examples

```text
Plan a cozy Saturday in New York at (40.7128, -74.0060). Include the current weather, 2 book ideas about mystery, one joke, and a dog pic.
```

```text
What is the temperature now at 22.308155, 70.800705? Is it likely to rain today?
```

```text
Give me one trivia question.
```

After a trivia question, enter your answer and Weekend Wizard checks it against the answer returned by the trivia API.

## Tools

- `get_weather`: current temperature, wind, and today's rain probability from Open-Meteo
- `book_recs`: book recommendations from Open Library
- `random_joke`: safe one-line joke from JokeAPI
- `random_dog`: random dog image URL from Dog CEO
- `trivia`: multiple-choice question from Open Trivia DB
