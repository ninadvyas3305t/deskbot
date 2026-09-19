"""DeskBot AI command brain using NVIDIA Nemotron."""

from __future__ import annotations

import os
import sys

from openai import OpenAI


MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
BASE_URL = "https://integrate.api.nvidia.com/v1"


SYSTEM_PROMPT = """
You are the command brain for DeskBot, a Windows desktop voice assistant.

Your job is to understand the user's natural-language command and return
ONE concise JSON object describing the intended action.

Supported actions:

1. open_app
2. open_website
3. youtube_search
4. youtube_play
5. spotify_open
6. unknown

Rules:

- Understand natural variations and casual speech.
- "yt", "u tube", and "youtube" mean YouTube.
- Do not treat vague filler such as "some music", "something", or
  "anything" as a literal search query.
- For vague music requests, use a null query.
- Extract the actual requested search/play subject when one exists.
- Never invent a query that the user did not provide.
- Return JSON only.
- Do not use Markdown.
- Do not add explanations.
-For open_app, always use the key "query" for the application name.
 Never use the key "app".

 Example:
 {
   "action": "open_app",
   "query": "Notepad"
 }
- For open_app, the "query" value must contain the application name.

JSON format:

{
  "action": "youtube_search",
  "query": "lofi music"
}

For a vague request such as:
"open youtube and play some music"

return:

{
  "action": "youtube_play",
  "query": null
}
"""


def create_client() -> OpenAI:
    """Create the NVIDIA API client."""
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set in the current terminal."
        )

    return OpenAI(
        base_url=BASE_URL,
        api_key=api_key,
    )


def understand(command: str) -> str:
    """Send a voice command to Nemotron and return its JSON response."""

    client = create_client()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": command,
            },
        ],
        temperature=0,
        max_tokens=200,
    )

    result = response.choices[0].message.content

    if not result:
        raise RuntimeError("Nemotron returned an empty response.")

    return result.strip()


def main() -> int:
    command = " ".join(sys.argv[1:]).strip()

    if not command:
        print("Usage: python ai_brain.py <command>")
        return 1

    try:
        result = understand(command)
    except Exception as error:
        print(f"AI brain error: {error}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())