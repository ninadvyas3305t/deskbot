"""DeskBot AI command brain using NVIDIA Nemotron."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import Any, List, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
BASE_URL = "https://integrate.api.nvidia.com/v1"

VALID_ACTIONS = {
    "open_app",
    "open_website",
    "youtube_search",
    "youtube_play",
    "spotify_open",
    "spotify_play",
    "volume_up",
    "volume_down",
    "mute",
    "unmute",
    "screenshot",
    "close_app",
    "open_folder",
    "open_file_explorer",
    "create_file",
    "create_folder",
    "delete_file",
    "delete_folder",
    "open_file",
    "open_in_vscode",
    "open_project_in_vscode",
    "direct_answer",
    "calculate",
    "web_search",
    "current_time",
    "current_date",
    "system_info",
    "weather",
    "unknown",
}

SYSTEM_PROMPT = """
You are the command brain for DeskBot, a Windows desktop voice assistant.

Your job is to understand the user's natural-language command and return
EXACTLY ONE JSON object describing the intended action.

Supported actions:

1. direct_answer: Answer general knowledge questions, definitions, science, math, explanations, or programming questions directly using your own reasoning.
   {"action": "direct_answer", "response": "The square root of 64 is 8."}
   {"action": "direct_answer", "response": "A neural network is a machine learning model inspired by the structure of biological neurons."}
2. calculate: Evaluate an arithmetic or math calculation.
   {"action": "calculate", "query": "25 * 16"}
3. open_file_explorer: Open Windows File Explorer.
   {"action": "open_file_explorer"}
4. open_folder: Open a specific folder by name or path (Downloads, Documents, Desktop, Pictures, Projects, DeskBot, etc.).
   {"action": "open_folder", "query": "Downloads"}
5. create_file: Create a file on Desktop or specified location.
   {"action": "create_file", "query": "notes.txt on my Desktop"}
6. create_folder: Create a folder on Desktop or specified location.
   {"action": "create_folder", "query": "Test inside my Desktop"}
7. delete_file: Delete a file safely from Desktop or specified location.
   {"action": "delete_file", "query": "notes.txt on my Desktop"}
8. delete_folder: Delete a folder safely from Desktop or specified location.
   {"action": "delete_folder", "query": "Test on my Desktop"}
9. open_file: Open a file with its default system app (e.g. text file, image, document).
   {"action": "open_file", "query": "test.txt"}
8. open_in_vscode: Open a file or folder in VS Code (e.g. "open main.py in VS Code", "open ai_brain.py", "open this folder in VS Code").
   {"action": "open_in_vscode", "query": "main.py"}
9. open_project_in_vscode: Open the DeskBot project folder in VS Code.
   {"action": "open_project_in_vscode"}
10. open_app: Open an application (e.g. "open notepad", "launch calculator", "start epic games").
   {"action": "open_app", "query": "Notepad"}
11. open_website: Open a website or domain (e.g. "open youtube", "open google.com").
   {"action": "open_website", "query": "youtube.com"}
12. youtube_search: Search YouTube (e.g. "search youtube for tutorials").
   {"action": "youtube_search", "query": "tutorials"}
13. youtube_play: Play a song, video, artist, or music.
   {"action": "youtube_play", "query": "Bohemian Rhapsody"}
   (or {"action": "youtube_play", "query": null} for vague "play music")
14. spotify_open: Open the Spotify desktop application.
   {"action": "spotify_open"}
15. spotify_play: Play music specifically on Spotify.
   {"action": "spotify_play", "query": "Starboy"}
16. volume_up: Increase system volume / make it louder.
   {"action": "volume_up"}
17. volume_down: Decrease system volume / make it quieter.
   {"action": "volume_down"}
18. mute: Mute system audio / sound.
   {"action": "mute"}
19. unmute: Unmute system audio.
   {"action": "unmute"}
20. screenshot: Take a screenshot of the desktop screen.
   {"action": "screenshot"}
21. close_app: Close an application safely (e.g. "close spotify", "quit notepad", "exit chrome").
   {"action": "close_app", "query": "Spotify"}
22. web_search: Search the web / internet ONLY when explicitly requested or for live real-time information (e.g. "search the web for...", "google...", "what's the latest NVIDIA GPU?").
   {"action": "web_search", "query": "what is the latest NVIDIA GPU"}
23. current_time: Ask for the current time.
   {"action": "current_time"}
24. current_date: Ask for the current date or day.
   {"action": "current_date"}
25. system_info: Check PC performance, CPU usage, RAM usage, or battery status.
   {"action": "system_info"}
26. weather: Check current weather.
   {"action": "weather", "query": "Tokyo"} (or {"action": "weather", "query": null} for local)
27. unknown: Returned if the command cannot be mapped to any supported action.
   {"action": "unknown"}


CRITICAL RULES:

1. DIRECT ANSWER VS WEB SEARCH (CRITICAL):
   - For ordinary knowledge, definitions, explanations, science, history, coding questions, and math:
     You MUST choose "direct_answer" and provide a concise, friendly spoken response in the "response" field (1-2 sentences, ready for text-to-speech).
     DO NOT choose "web_search" for questions you can answer directly.
   - ONLY choose "web_search" if the user explicitly asks to search the web/google (e.g. "search the web for...", "google..."), or asks about live current events / real-time news / live prices (e.g. "latest NVIDIA GPU", "today's news", "current price of Bitcoin").

2. DEFAULT MUSIC/VIDEO PLATFORM:
   - When the user asks to play a song, video, artist, or music WITHOUT explicitly specifying Spotify (e.g. "play Bohemian Rhapsody", "play Loser by Tame Impala", "play some music", "play Starboy"), you MUST ALWAYS choose "youtube_play".
   - ONLY choose "spotify_play" if the user explicitly mentions Spotify (e.g. "play Starboy on Spotify", "play it on Spotify").

3. STRICT FORMATTING:
   - Output ONLY the raw JSON object.
   - Do NOT include any explanations, internal reasoning, chain-of-thought, or markdown codeblocks.
   - The very first character of your response MUST be '{' and the last character MUST be '}'.

4. ACTION DETAILS:
   - For direct_answer, provide the natural concise answer in the "response" field.
   - For open_app, always use the key "query" for the application name (e.g. "Notepad", "Calculator", "Task Manager", "Paint", "Settings", "Epic Games", "Chrome"). Never use "app".
   - For close_app, always use "query" for the application name to terminate.
   - For open_folder, use "query" for the folder name (e.g. "Downloads", "Documents", "Projects").
   - For web_search, use "query" for the search query/terms.
   - For weather, use "query" for the city/location (e.g. "Tokyo", "London"), or null for local.

5. CONVERSATION CONTEXT & PRONOUN RESOLUTION:
   - Resolve pronouns ("it", "that", "that song", "close it") using recent conversation turns if provided.
   - For example: if user opened Spotify in previous turn and says "close it", return {"action": "close_app", "query": "Spotify"}.
   - If user asked about weather in Tokyo and then says "What about London?", return {"action": "weather", "query": "London"}.

JSON format:

{
  "action": "direct_answer",
  "response": "The square root of 64 is 8."
}
"""


_CONVERSATION_TURNS: List[dict[str, str]] = []


def reset_history() -> None:
    """Clear conversational turn history."""
    _CONVERSATION_TURNS.clear()


def create_client() -> OpenAI:
    """Create the NVIDIA API client."""
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not set in the current environment."
        )

    return OpenAI(
        base_url=BASE_URL,
        api_key=api_key,
    )


def validate_intent(intent: Any) -> Tuple[bool, str]:
    """Validate parsed JSON intent against the expected schema."""
    if not isinstance(intent, dict):
        return False, "Intent must be a JSON dictionary."

    action = intent.get("action")
    if not action or not isinstance(action, str):
        return False, "Intent missing valid 'action' field."

    if action not in VALID_ACTIONS:
        return False, f"Unsupported action: '{action}'"

    return True, ""


def resolve_contextual_target(reference_text: str, is_folder: bool = False) -> str | None:
    """Resolve anaphoric phrases like 'that you just created', 'it', 'that file' from recent turns."""
    clean_ref = reference_text.strip().lower().strip(".,?!;:`'\"")
    clean_ref = re.sub(r"^(?:the\s+)?(?:file|folder)\s+", "", clean_ref)

    contextual_patterns = [
        r"^(?:that\s+)?(?:you\s+|i\s+)?(?:just\s+)?created$",
        r"^(?:the\s+one\s+)?(?:that\s+)?(?:you\s+|i\s+)?(?:just\s+)?created$",
        r"^(?:the\s+)?(?:file|folder)\s+(?:that\s+)?(?:you\s+|i\s+)?(?:just\s+)?created$",
        r"^(?:it|that|that\s+file|this\s+file|the\s+file|that\s+folder|this\s+folder|the\s+folder)$",
        r"^just\s+created$",
    ]
    if not any(re.match(pat, clean_ref) for pat in contextual_patterns):
        return None

    # Search backward through recent conversational turns
    for turn in reversed(_CONVERSATION_TURNS):
        content = turn.get("content", "")
        # Check for created file in assistant message: "Created <file> on your Desktop" or "Created folder <folder>"
        m_created = re.search(r"\bCreated\s+(?:folder\s+)?([a-zA-Z0-9_\-.]+(?:\.[a-zA-Z0-9]{1,5})?)", content, flags=re.IGNORECASE)
        if m_created:
            cand = m_created.group(1).strip()
            if not is_folder:
                if "." in cand:
                    return cand
            else:
                return cand

        # Check for filename with extension mentioned in recent turn
        m_file = re.search(r"\b([a-zA-Z0-9_\-.]+\.[a-zA-Z0-9]{1,5})\b", content)
        if m_file and not is_folder:
            return m_file.group(1).strip()

        # Check for folder mentioned in recent turn
        if is_folder:
            m_folder = re.search(r"\b(?:folder|directory)\s+([a-zA-Z0-9_\-]+)", content, flags=re.IGNORECASE)
            if m_folder:
                return m_folder.group(1).strip()

    return None


def extract_json_intent(raw_text: str, user_command: str) -> dict | None:
    """Extract or reconstruct a valid intent dict from raw text."""
    raw_str = (raw_text or "").strip()
    user_cmd = (user_command or "").strip()

    if not raw_str and not user_cmd:
        return None

    if raw_str:
        cleaned = raw_str
        # Strip markdown fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # Fix doubled braces like {"{"action":...
        cleaned = re.sub(r'^\{\s*["\']?\{', "{", cleaned)

        # 1. Try direct JSON parsing
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                # Check if nested {"action": {"action": ...}}
                if isinstance(data.get("action"), dict):
                    inner = data["action"]
                    if "action" in inner:
                        return inner
                return data
        except Exception:
            pass

        # 2. Try extracting JSON substring {...}
        match = re.search(r"\{[\s\S]*?\}", cleaned)
        if match:
            candidate = match.group(0)
            candidate = re.sub(r'^\{\s*["\']?\{', "{", candidate)
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    if isinstance(data.get("action"), dict):
                        inner = data["action"]
                        if "action" in inner:
                            if inner.get("action") == "direct_answer" and "response" not in inner and "query" in inner:
                                inner["response"] = inner["query"]
                            return inner
                    if data.get("action") == "direct_answer" and "response" not in data and "query" in data:
                        data["response"] = data["query"]
                    return data
            except Exception:
                pass

        # 3. Direct regex key-value extraction: extracts "action" and "query"/"response" even if JSON is broken/unclosed
        action_match = re.search(r'["\']action["\']\s*:\s*["\']([a-zA-Z0-9_]+)["\']', raw_str)
        if action_match:
            act = action_match.group(1).lower()
            if act in VALID_ACTIONS:
                val_match = re.search(
                    r'["\'](?:query|response)["\']\s*:\s*(?:["\']([^"\']*)["\']|(null)|(None))',
                    raw_str,
                    flags=re.IGNORECASE,
                )
                val = None
                if val_match and val_match.group(1) is not None:
                    val = val_match.group(1)
                if act == "direct_answer":
                    return {"action": act, "response": val}
                return {"action": act, "query": val}

    # 4. Fallback heuristics based on user_command and raw_text
    lower_raw = raw_str.lower()
    lower_cmd = user_cmd.lower().strip()
    cleaned_speech = re.sub(r"^(?:hey\s+jarvis\s*,?\s*)?(?:no\s*,?\s*|nope\s*,?\s*)?(?:please\s+)?(?:can\s+you\s+)?", "", lower_cmd).strip()
    orig_speech = re.sub(r"^(?:hey\s+jarvis\s*,?\s*)?(?:no\s*,?\s*|nope\s*,?\s*)?(?:please\s+)?(?:can\s+you\s+)?", "", user_cmd, flags=re.IGNORECASE).strip()

    # Strip trailing punctuation produced by STT
    cleaned_speech = cleaned_speech.rstrip(".,?!;:`'\"").strip()
    orig_speech = orig_speech.rstrip(".,?!;:`'\"").strip()

    # Normalize spoken extensions (e.g. "notes dot txt" -> "notes.txt", "main dot py" -> "main.py")
    orig_speech = re.sub(r"\s+dot\s+([a-zA-Z0-9]+)\b", r".\1", orig_speech, flags=re.IGNORECASE)
    cleaned_speech = re.sub(r"\s+dot\s+([a-zA-Z0-9]+)\b", r".\1", cleaned_speech, flags=re.IGNORECASE)

    # Rule 00: Safe deterministic math & calculations
    try:
        from tools.calculator import evaluate_math
        math_eval = evaluate_math(cleaned_speech)
        if math_eval:
            return {"action": "direct_answer", "response": math_eval}
    except Exception:
        pass


    # Rule 0-DEL: Delete file or folder
    del_folder_match = re.search(r"\b(?:delete|remove|erase)\s+(?:the\s+)?(?:folder|directory)\s+(?:called\s+|named\s+)?(.+)", orig_speech, flags=re.IGNORECASE)
    if del_folder_match:
        target = del_folder_match.group(1).strip()
        contextual = resolve_contextual_target(target, is_folder=True)
        if contextual:
            return {"action": "delete_folder", "query": contextual}
        if not any(re.search(pat, target.lower()) for pat in [r"\bjust\s+created\b", r"\byou\s+created\b", r"^it$", r"^that$"]):
            return {"action": "delete_folder", "query": target}

    del_file_match = re.search(r"\b(?:delete|remove|erase)\s+(?:the\s+)?(?:file\s+)?(?:called\s+|named\s+)?(.+)", orig_speech, flags=re.IGNORECASE)
    if del_file_match:
        target = del_file_match.group(1).strip()
        target = re.sub(r"^(?:file|called|named)\s+", "", target, flags=re.IGNORECASE).strip()
        if re.match(r"^(?:folder|directory)\s+", target, flags=re.IGNORECASE):
            target = re.sub(r"^(?:folder|directory)\s+", "", target, flags=re.IGNORECASE).strip()
            contextual = resolve_contextual_target(target, is_folder=True)
            if contextual:
                return {"action": "delete_folder", "query": contextual}
            return {"action": "delete_folder", "query": target}

        contextual = resolve_contextual_target(target, is_folder=False)
        if contextual:
            return {"action": "delete_file", "query": contextual}

        contextual_check = target.lower().strip(".,?!;:`'\"")
        is_contextual = any(re.search(pat, contextual_check) for pat in [
            r"\bjust\s+created\b", r"\byou\s+created\b", r"^it$", r"^that$", r"^that\s+file$", r"^this\s+file$"
        ])
        if not is_contextual:
            return {"action": "delete_file", "query": target}

    # Rule 0-CONFIRM: Handle affirmative confirmation after a question
    if re.match(r"^(?:yes|proceed|confirm|go\s+ahead|do\s+it|yes\s+delete\s+it|delete\s+it)$", cleaned_speech):
        for turn in reversed(_CONVERSATION_TURNS):
            if turn.get("role") == "assistant":
                content = turn.get("content", "")
                m = re.search(r"delete\s+([^.?]+)", content, flags=re.IGNORECASE)
                if m:
                    cand = m.group(1).strip()
                    return {"action": "delete_file", "query": cand}
                break

    # Rule 0-EXPLORER: Open File Explorer
    if re.search(r"\b(?:open|launch|show)\s+(?:(?:windows|file)\s+)?explorer\b", cleaned_speech) or \
       cleaned_speech in {"open explorer", "explorer", "file explorer"}:
        return {"action": "open_file_explorer"}

    # Rule 0-CREATE-FILE: Create file
    create_file_match = re.search(r"\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?file\s+(?:called\s+|named\s+)?(.+)", orig_speech, flags=re.IGNORECASE)
    if create_file_match:
        target = create_file_match.group(1).strip()
        return {"action": "create_file", "query": target}

    # Rule 0-CREATE-FOLDER: Create folder
    create_folder_match = re.search(r"\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+(?:called\s+|named\s+)?(.+)", orig_speech, flags=re.IGNORECASE)
    if create_folder_match:
        target = create_folder_match.group(1).strip()
        return {"action": "create_folder", "query": target}

    # Rule 0A-VSCODE-TARGET: Open specific target in VS Code
    vscode_target_match = re.search(r"\b(?:open|launch)\s+(.+?)\s+in\s+(?:vs\s*code|vscode|code)\b", orig_speech, flags=re.IGNORECASE)
    if vscode_target_match:
        target = vscode_target_match.group(1).strip()
        if target.lower() in {"deskbot", "the deskbot project", "deskbot project", "the project", "project", "codebase", "workspace", "this folder"}:
            return {"action": "open_project_in_vscode"}
        return {"action": "open_in_vscode", "query": target}

    # Rule 0A: VS Code project launcher
    if re.search(r"\b(?:open|launch)\s+(?:the\s+|my\s+)?(?:deskbot\s+)?(?:project|codebase)(?:\s+in\s+(?:vs\s*code|vscode|code))?\b", cleaned_speech) or \
       re.search(r"\b(?:open|launch)\s+(?:vs\s*code|vscode)\b", cleaned_speech):
        return {"action": "open_project_in_vscode"}

    # Rule 0-OPEN-FILE-EXPLICIT: Open file explicitly
    open_file_match = re.search(r"\b(?:open|launch)\s+(?:the\s+)?file\s+(?:called\s+|named\s+)?(.+)", orig_speech, flags=re.IGNORECASE)
    if open_file_match:
        target = open_file_match.group(1).strip()
        return {"action": "open_file", "query": target}

    # Rule 0-EXT: Check file extensions (code -> vscode, docs/others -> open_file)
    ext_match = re.match(r"^(?:open|launch)\s+(?:the\s+)?([a-zA-Z0-9_\-/\\]+\.([a-zA-Z0-9]{1,5}))(?:\s+(?:on|in|inside)(?:\s+my)?\s+[a-zA-Z0-9_\- ]+)?$", orig_speech, flags=re.IGNORECASE)
    if ext_match:
        full_file_spec = re.sub(r"^(?:open|launch)\s+(?:the\s+)?", "", orig_speech, flags=re.IGNORECASE).strip()
        ext = ext_match.group(2).lower()
        if ext in {"py", "cpp", "c", "h", "hpp", "json", "toml", "yaml", "yml", "ini", "md"}:
            return {"action": "open_in_vscode", "query": full_file_spec}
        elif ext in {"txt", "pdf", "docx", "doc", "png", "jpg", "jpeg", "csv", "log"}:
            return {"action": "open_file", "query": full_file_spec}

    # Rule 0B: Open safe folders
    folder_match = re.search(r"\b(?:open|show|explore)(?:\s+my)?\s+(downloads|documents|pictures|desktop|videos|music|projects|deskbot)(?:\s+folder|\s+directory)?\b", cleaned_speech)
    if folder_match:
        return {"action": "open_folder", "query": folder_match.group(1)}

    # Rule 0C: Volume / Audio Controls
    if re.search(r"\b(?:unmute|un-mute)\b", cleaned_speech):
        return {"action": "unmute"}
    if re.search(r"\b(?:mute|silence)\b", cleaned_speech):
        return {"action": "mute"}
    if re.search(r"\b(?:volume\s*(?:up|increase|raise|boost|higher)|louder|turn\s*it\s*up)\b", cleaned_speech):
        return {"action": "volume_up"}
    if re.search(r"\b(?:volume\s*(?:down|decrease|lower|drop|softer|quieter)|softer|quieter|turn\s*it\s*down)\b", cleaned_speech):
        return {"action": "volume_down"}

    # Rule 0D: Screenshot
    if re.search(r"\b(?:take\s*(?:a\s*)?)?screenshot\b|\bcapture\s*(?:the\s*)?screen\b", cleaned_speech):
        return {"action": "screenshot"}

    # Rule 0E: Close app
    close_match = re.search(r"^(?:close|quit|exit|kill|terminate)(?:\s+(?:the|app|application))?\s+([a-zA-Z0-9_\- ]+)", cleaned_speech)
    if close_match:
        target = close_match.group(1).strip()
        target = re.sub(r"\s+app(?:lication)?$", "", target).strip()
        if target:
            return {"action": "close_app", "query": target.title()}

    # Rule 0F: Real-time info (Time, Date, System, Weather)
    if re.search(r"\b(?:what\s*(?:'s|\s+is)\s+the\s+time|what\s+time\s+is\s+it|tell\s+me\s+the\s+time|current\s+time)\b", cleaned_speech):
        return {"action": "current_time"}
    if re.search(r"\b(?:what\s*(?:'s|\s+is)\s+today(?:'s)?\s+date|what\s+date\s+is\s+it|what\s+day\s+is\s+it|current\s+date)\b", cleaned_speech):
        return {"action": "current_date"}
    if re.search(r"\b(?:system\s+(?:info|metrics|status)|cpu\s+usage|battery\s+(?:level|status|percent)|ram\s+usage|memory\s+usage)\b", cleaned_speech):
        return {"action": "system_info"}

    weather_match = re.search(r"\b(?:what\s*(?:'s|\s+is)\s+the\s+weather|check\s+weather|how\s*(?:'s|\s+is)\s+the\s+weather)(?:\s+in\s+([a-zA-Z\s]+))?\b", cleaned_speech)
    if weather_match:
        city = weather_match.group(1)
        return {"action": "weather", "query": city.strip().title() if city else None}

    # Rule 0G: Web search
    search_match = re.search(r"\b(?:search\s+(?:the\s+web|google)\s+for|search\s+for|google\s+)(.+)", cleaned_speech)
    if search_match:
        q_search = search_match.group(1).strip()
        if q_search:
            return {"action": "web_search", "query": q_search}

    # Rule A: Open app / Open website
    if re.match(r"^(?:open|launch|start|run)(?:\s+up)?\s+", cleaned_speech):
        target = re.sub(r"^(?:open|launch|start|run)(?:\s+up)?\s+", "", cleaned_speech).strip()
        target = re.sub(r"^(?:the\s+)?", "", target).strip()
        target = re.sub(r"\s+app(?:lication)?$", "", target).strip()
        if target in {"spotify"}:
            return {"action": "spotify_open"}
        if target in {"youtube", "yt", "google"}:
            return {"action": "open_website", "query": target}
        if target:
            return {"action": "open_app", "query": target.title()}

    # Rule B: Specific play commands
    if "spotify_play" in lower_raw or ("play" in lower_cmd and "spotify" in lower_cmd):
        q = re.sub(r"^(?:hey\s+jarvis\s*,?\s*)?(?:just\s+)?play\s+(?:the\s+song\s+)?", "", user_command, flags=re.IGNORECASE).strip()
        q = re.sub(r"\s+(?:on|in|using)\s+spotify$", "", q, flags=re.IGNORECASE).strip()
        if q.lower() in {"it", "that", "that song", ""}:
            # Resolve from context if available
            for turn in reversed(_CONVERSATION_TURNS):
                if turn.get("role") == "assistant":
                    try:
                        prev = json.loads(turn.get("content", "{}"))
                        if prev.get("query"):
                            q = prev["query"]
                            break
                    except Exception:
                        pass
        return {"action": "spotify_play", "query": q if q else None}

    if "youtube_play" in lower_raw or "play" in lower_cmd:
        q = re.sub(r"^(?:hey\s+jarvis\s*,?\s*)?(?:just\s+)?play\s+(?:the\s+song\s+)?", "", user_command, flags=re.IGNORECASE).strip()
        q = re.sub(r"\s+(?:on|in|using)\s+youtube$", "", q, flags=re.IGNORECASE).strip()
        return {"action": "youtube_play", "query": q if q else None}

    if "spotify_open" in lower_raw or "spotify" in lower_cmd:
        return {"action": "spotify_open"}

    return None


def fast_intent_match(user_command: str) -> dict | None:
    """Fast-path deterministic intent parser.

    Bypasses cloud LLM network roundtrips for local system utilities, time, date,
    screenshots, volume, math, app opening/closing, and filesystem operations.
    Returns a valid intent dict in <1ms, or None for general questions/reasoning.
    """
    if not user_command or not user_command.strip():
        return None

    # Evaluate local heuristic rules directly on the voice command
    intent = extract_json_intent("", user_command)
    if intent and isinstance(intent, dict):
        action = intent.get("action")
        if action in VALID_ACTIONS and action != "unknown":
            valid, _ = validate_intent(intent)
            if valid:
                return intent

    return None


def understand(command: str, context_prompt: str = "") -> str:
    """Send a voice command to Nemotron with recent context and return its raw JSON string response."""
    client = create_client()

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
    ]
    if context_prompt:
        messages.append(
            {
                "role": "system",
                "content": context_prompt,
            }
        )
    # Include up to the last 2 turns (4 messages) for context resolution
    messages.extend(_CONVERSATION_TURNS[-4:])
    messages.append(
        {
            "role": "user",
            "content": command,
        }
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    result = response.choices[0].message.content

    if not result:
        raise RuntimeError("Nemotron returned an empty response.")

    clean_result = result.strip()

    # Track turns for context resolution in subsequent commands
    _CONVERSATION_TURNS.append({"role": "user", "content": command})
    _CONVERSATION_TURNS.append({"role": "assistant", "content": clean_result})
    if len(_CONVERSATION_TURNS) > 6:
        del _CONVERSATION_TURNS[:-6]

    return clean_result


def understand_intent(command: str, context_prompt: str = "") -> dict | None:
    """Send voice command to Nemotron, parse JSON, and validate against intent schema.

    Returns valid intent dict on success, or fallback heuristic intent, or None on failure.
    """
    try:
        raw_result = understand(command, context_prompt=context_prompt)
    except Exception as error:
        # Check if fallback local heuristics can answer
        fallback = extract_json_intent("", command)
        if fallback:
            valid, _ = validate_intent(fallback)
            if valid:
                return fallback

        if not os.getenv("NVIDIA_API_KEY"):
            logger.warning("NVIDIA_API_KEY is not set. Cloud AI reasoning is disabled.")
            return {
                "action": "direct_answer",
                "response": "I didn't recognize that command, and the NVIDIA API key is not set for online questions.",
            }

        logger.error("AI brain API request failed: %s", error)
        return None

    parsed = extract_json_intent(raw_result, command)
    if not parsed:
        logger.error("Could not extract intent from AI response: %r", raw_result)
        return None

    valid, reason = validate_intent(parsed)
    if not valid:
        logger.warning("AI intent validation failed: %s (received: %r)", reason, parsed)
        return {"action": "unknown", "query": None}

    return parsed


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