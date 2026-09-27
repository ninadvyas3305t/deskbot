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
    "clarification",
    "enter_developer_mode",
    "exit_developer_mode",
    "get_active_window",
    "get_current_file",
    "get_current_workspace",
    "list_workspace_files",
    "search_workspace",
    "read_active_file",
    "analyze_code",
    "run_tests",
    "apply_patch",
    "rollback_patch",
    "unknown",
}

SYSTEM_PROMPT = """
You are the intelligent command brain for DeskBot, a Windows voice assistant.

Your job is to understand the user's natural-language command and return
EXACTLY ONE JSON object classifying the intent and describing the action.

Intent Categories:

1. DIRECT_ANSWER:
   - For general knowledge, definitions, math, science, explanations, programming, geography, and history.
   - The assistant already knows these facts from its training. DO NOT search the web!
   - Provide a natural, concise spoken answer in the "response" field (1-3 sentences, ready for text-to-speech).
   - Examples:
     * "What is the capital of India?" -> {"type": "DIRECT_ANSWER", "action": "direct_answer", "response": "The capital of India is New Delhi."}
     * "What is the square root of 64?" -> {"type": "DIRECT_ANSWER", "action": "direct_answer", "response": "The square root of 64 is 8."}
     * "What is a neural network?" -> {"type": "DIRECT_ANSWER", "action": "direct_answer", "response": "A neural network is a machine learning model inspired by the structure of biological neurons."}
     * "Explain PCA." -> {"type": "DIRECT_ANSWER", "action": "direct_answer", "response": "PCA, or Principal Component Analysis, is a technique used to reduce the dimensionality of large datasets while preserving as much variance as possible."}
     * "What does HTTP stand for?" -> {"type": "DIRECT_ANSWER", "action": "direct_answer", "response": "HTTP stands for Hypertext Transfer Protocol."}
     * "Who invented the telephone?" -> {"type": "DIRECT_ANSWER", "action": "direct_answer", "response": "Alexander Graham Bell is widely credited with inventing the first practical telephone."}

2. WEB_SEARCH (CURRENT_INFORMATION):
   - Use ONLY when external, real-time, or current information is required that depends on what is happening now, today, or recently.
   - Indicator words: "latest", "today", "right now", "currently", "recent", "this week", "this month", breaking news, live events, sports scores, market prices.
   - FOLLOW-UP CONTEXT RULE: If recent conversation was discussing a specific topic (e.g. news in India) and the user asks a follow-up (e.g. "Tell me about sports news"), incorporate the topic into the search query (e.g. "latest sports news India").
   - Examples:
     * "Can you tell me the news in India?" -> {"type": "WEB_SEARCH", "action": "web_search", "query": "latest news in India"}
     * "Tell me about sports news." (after India news) -> {"type": "WEB_SEARCH", "action": "web_search", "query": "latest sports news India"}
     * "Is there any special event happening in India right now?" -> {"type": "WEB_SEARCH", "action": "web_search", "query": "major events in India today right now"}
     * "What happened in cricket today?" -> {"type": "WEB_SEARCH", "action": "web_search", "query": "cricket news scores today"}
     * "What is the current price of Bitcoin?" -> {"type": "WEB_SEARCH", "action": "web_search", "query": "current price of Bitcoin USD"}
     * "What's the latest NVIDIA news?" -> {"type": "WEB_SEARCH", "action": "web_search", "query": "latest NVIDIA news announcements"}

3. TOOL_CALL:
   - For local desktop and PC system operations:
     * open_app: {"type": "TOOL_CALL", "action": "open_app", "query": "Notepad"}
     * close_app: {"type": "TOOL_CALL", "action": "close_app", "query": "Spotify"}
     * create_file: {"type": "TOOL_CALL", "action": "create_file", "query": "notes.txt on my Desktop"}
     * delete_file: {"type": "TOOL_CALL", "action": "delete_file", "query": "notes.txt on my Desktop"}
     * create_folder: {"type": "TOOL_CALL", "action": "create_folder", "query": "Test on Desktop"}
     * delete_folder: {"type": "TOOL_CALL", "action": "delete_folder", "query": "Test on Desktop"}
     * open_file: {"type": "TOOL_CALL", "action": "open_file", "query": "test.txt"}
     * open_folder: {"type": "TOOL_CALL", "action": "open_folder", "query": "Downloads"}
     * open_file_explorer: {"type": "TOOL_CALL", "action": "open_file_explorer"}
     * open_in_vscode: {"type": "TOOL_CALL", "action": "open_in_vscode", "query": "main.py"}
     * open_project_in_vscode: {"type": "TOOL_CALL", "action": "open_project_in_vscode"}
     * screenshot: {"type": "TOOL_CALL", "action": "screenshot"}
     * volume_up: {"type": "TOOL_CALL", "action": "volume_up"}
     * volume_down: {"type": "TOOL_CALL", "action": "volume_down"}
     * mute: {"type": "TOOL_CALL", "action": "mute"}
     * unmute: {"type": "TOOL_CALL", "action": "unmute"}
     * youtube_play: {"type": "TOOL_CALL", "action": "youtube_play", "query": "Bohemian Rhapsody"}
     * youtube_search: {"type": "TOOL_CALL", "action": "youtube_search", "query": "guitar tutorials"}
     * spotify_play: {"type": "TOOL_CALL", "action": "spotify_play", "query": "Starboy"}
     * spotify_open: {"type": "TOOL_CALL", "action": "spotify_open"}
     * open_website: {"type": "TOOL_CALL", "action": "open_website", "query": "youtube.com"}
     * current_time: {"type": "TOOL_CALL", "action": "current_time"}
     * current_date: {"type": "TOOL_CALL", "action": "current_date"}
     * system_info: {"type": "TOOL_CALL", "action": "system_info"}
     * weather: {"type": "TOOL_CALL", "action": "weather", "query": "Tokyo"}
     * calculate: {"type": "TOOL_CALL", "action": "calculate", "query": "25 * 16"}

4. CLARIFICATION:
   - Use only when user request is too underspecified to proceed safely:
     {"type": "CLARIFICATION", "action": "clarification", "question": "Which file would you like me to delete?", "response": "Which file would you like me to delete?"}

CRITICAL RULES:
1. NEVER use "web_search" for questions you can answer directly (math, science, definitions, stable knowledge).
2. ONLY use "web_search" for live/current events, breaking news, or explicit web queries.
3. Output ONLY the raw JSON object. The first character must be '{' and last character must be '}'.
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
    """Validate parsed JSON intent against the expected schema and normalize intent taxonomy."""
    if not isinstance(intent, dict):
        return False, "Intent must be a JSON dictionary."

    # Normalize type -> action if action was omitted
    if "type" in intent and "action" not in intent:
        intent_type = str(intent["type"]).upper().strip()
        if intent_type == "DIRECT_ANSWER":
            intent["action"] = "direct_answer"
        elif intent_type in {"WEB_SEARCH", "CURRENT_INFORMATION"}:
            intent["action"] = "web_search"
        elif intent_type == "CLARIFICATION":
            intent["action"] = "clarification"

    action = intent.get("action")
    if not action or not isinstance(action, str):
        return False, "Intent missing valid 'action' field."

    if action not in VALID_ACTIONS:
        return False, f"Unsupported action: '{action}'"

    return True, ""


def get_intent_type(intent: dict) -> str:
    """Get standardized intent category (DIRECT_ANSWER, WEB_SEARCH, TOOL_CALL, CLARIFICATION)."""
    if not isinstance(intent, dict):
        return "UNKNOWN"
    if "type" in intent and intent["type"]:
        return str(intent["type"]).upper().strip()
    action = intent.get("action", "")
    if action == "direct_answer":
        return "DIRECT_ANSWER"
    if action == "web_search":
        return "WEB_SEARCH"
    if action == "clarification":
        return "CLARIFICATION"
    return "TOOL_CALL"


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
                if act in {"direct_answer", "clarification"}:
                    return {"action": act, "response": val}
                return {"action": act, "query": val}

    # 4. Fallback heuristics based on user_command and raw_text
    lower_raw = raw_str.lower()
    lower_cmd = user_cmd.lower().strip()
    prefix_pat = r"^(?:hey\s+jarvis\s*,?\s*)?(?:no\s*,?\s*|nope\s*,?\s*)?(?:please\s+)?(?:can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+|you\s+|just\s+|now\s+|and\s+)?"
    cleaned_speech = re.sub(prefix_pat, "", lower_cmd).strip()
    orig_speech = re.sub(prefix_pat, "", user_cmd, flags=re.IGNORECASE).strip()

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

    # Rule 0B: Open safe folders (screenshots, pictures, downloads, documents, desktop, etc.)
    is_open_intent = bool(re.search(r"\b(?:open|show|explore|view|browse|take\s+me\s+to|bring\s+up|where(?:\s+is|\s+are|\s+did|\s+your|\s+you)?)\b", cleaned_speech))

    if is_open_intent:
        # Check screenshot folder references first
        if re.search(r"\b(?:screenshots?|screen\s*shots?)\b", cleaned_speech):
            return {"action": "open_folder", "query": "screenshots"}

        # General safe folder opening: handles "open pictures folder", "open the folder pictures", "open downloads", etc.
        folder_pattern = r"\b(?:open|show|explore|view|browse)(?:\s+(?:my|the))?\s+(?:(?:folder|directory)\s+)?(downloads|documents|pictures|desktop|videos|music|projects|deskbot)(?:\s+(?:folder|directory))?\b"
        folder_match = re.search(folder_pattern, cleaned_speech)
        if folder_match:
            return {"action": "open_folder", "query": folder_match.group(1)}

        # Contextual folder reference: "open that folder for me to see", "open that folder", "open the folder you created"
        if re.search(r"\b(?:that|this|the\s+created|the\s+one\s+you\s+created)\s+(?:folder|directory)\b", cleaned_speech) or \
           re.search(r"\b(?:folder|directory)\s+(?:that\s+)?(?:you\s+|i\s+)?(?:just\s+)?created\b", cleaned_speech):
            return {"action": "open_folder", "query": "that folder"}

        # Specific named folder: "open the folder called X", "open folder named X", "open folder X"
        named_folder_match = re.search(
            r"\b(?:open|show|explore|view|browse)\s+(?:the\s+)?(?:folder|directory)\s+(?:called\s+(?:as\s+)?|named\s+(?:as\s+)?|with\s+(?:the\s+)?name\s+(?:of\s+)?|as\s+)?(.+)",
            orig_speech,
            flags=re.IGNORECASE,
        )
        if named_folder_match:
            cand_name = named_folder_match.group(1).strip()
            # Clean conversational filler: "for me to see", "for me", "to see", "please"
            cand_name = re.sub(r"\b(?:for\s+me(?:\s+to\s+see)?|to\s+see|please)\b", "", cand_name, flags=re.IGNORECASE).strip()
            cand_name = re.sub(r"^(?:called\s+(?:as\s+)?|named\s+(?:as\s+)?|as\s+)", "", cand_name, flags=re.IGNORECASE).strip()
            cand_name = cand_name.strip(".,?!;:`'\"")
            if cand_name and not any(cand_name.lower().startswith(k) for k in ("app", "website", "youtube", "spotify")):
                return {"action": "open_folder", "query": cand_name}

        # "<name> folder/directory": "open documents folder", "open NEDS folder"
        suffix_folder_match = re.search(r"\b(?:open|show|explore|view|browse)\s+(?:the\s+)?(.+?)\s+(?:folder|directory)\b", orig_speech, flags=re.IGNORECASE)
        if suffix_folder_match:
            cand_name = suffix_folder_match.group(1).strip()
            cand_name = re.sub(r"^(?:the|my)\s+", "", cand_name, flags=re.IGNORECASE).strip()
            if cand_name and not any(cand_name.lower().startswith(k) for k in ("app", "website")):
                return {"action": "open_folder", "query": cand_name}

    # Rule 0C: Volume / Audio Controls
    if re.search(r"\b(?:unmute|un-mute)\b", cleaned_speech):
        return {"action": "unmute"}
    if re.search(r"\b(?:mute|silence)\b", cleaned_speech):
        return {"action": "mute"}
    if re.search(r"\b(?:volume\s*(?:up|increase|raise|boost|higher)|louder|turn\s*it\s*up)\b", cleaned_speech):
        return {"action": "volume_up"}
    if re.search(r"\b(?:volume\s*(?:down|decrease|lower|drop|softer|quieter)|softer|quieter|turn\s*it\s*down)\b", cleaned_speech):
        return {"action": "volume_down"}

    # Rule 0D: Screenshot Capture (strictly requires capture verb or standalone screenshot, never triggers on open/view/where)
    if not is_open_intent and not re.search(r"\b(?:delete|remove|erase|where|find)\b", cleaned_speech):
        if re.search(r"\b(?:take|capture|grab|snap|make|shoot)(?:\s+(?:a|the))?\s+(?:screenshot|screen\s*shot|screen\s*capture)\b", cleaned_speech) or \
           re.search(r"\bcapture\s+(?:the\s+)?screen\b", cleaned_speech) or \
           cleaned_speech in {"screenshot", "take screenshot", "take a screenshot", "capture screen", "screen capture"}:
            return {"action": "screenshot"}

    # Rule DEV-MODE: Enter/exit developer mode
    if re.search(r"\b(?:enter|activate|turn\s+on|start|switch\s+to)\s+developer\s+mode\b", cleaned_speech) or \
       cleaned_speech in {"developer mode", "help me with my code", "help with my code", "help with code"}:
        return {"action": "enter_developer_mode"}
    if re.search(r"\b(?:exit|leave|deactivate|turn\s+off|stop|disable)\s+developer\s+mode\b", cleaned_speech) or \
       cleaned_speech in {"exit developer mode", "leave developer mode", "normal mode"}:
        return {"action": "exit_developer_mode"}

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

    # Rule DEV-WINDOW: Active window / Screen understanding
    if re.search(r"\b(?:what\s+(?:am\s+i|are\s+we)\s+looking\s+at|look\s+at\s+my\s+screen|inspect\s+(?:my\s+)?screen|what\s+window\s+is\s+(?:active|open)|what\s+app\s+is\s+(?:active|open))\b", cleaned_speech):
        return {"action": "get_active_window"}

    # Rule DEV-FILE: Current file detection
    if re.search(r"\b(?:what\s+file\s+am\s+i\s+working\s+on|what\s+file\s+is\s+open|which\s+file\s+is\s+open|what\s+is\s+the\s+active\s+file|current\s+file)\b", cleaned_speech):
        return {"action": "get_current_file"}

    # Rule DEV-WORKSPACE: Workspace info & file search
    if re.search(r"\b(?:what\s+workspace|what\s+project\s+am\s+i\s+in|current\s+workspace|current\s+project)\b", cleaned_speech):
        return {"action": "get_current_workspace"}

    dev_search_match = re.search(r"\b(?:search\s+workspace(?:\s+for)?|search\s+project(?:\s+for)?|search\s+code(?:\s+for)?|find\s+in\s+workspace)\s+(.+)", cleaned_speech)
    if dev_search_match:
        q_dev = dev_search_match.group(1).strip()
        if q_dev:
            return {"action": "search_workspace", "query": q_dev}

    where_match = re.search(r"\bwhere\s+is\s+(?:the\s+)?([a-zA-Z0-9_\-]+)\s+(?:handled|defined|located|implemented)\b", cleaned_speech)
    if where_match:
        return {"action": "search_workspace", "query": where_match.group(1)}

    # Rule DEV-TESTS: Run unit tests
    if re.search(r"\b(?:run\s+(?:the\s+)?(?:unit\s+)?tests?|run\s+test\s+suite|test\s+(?:the\s+)?project)\b", cleaned_speech):
        return {"action": "run_tests"}

    # Rule DEV-READ: Read/explain active file
    if re.search(r"\b(?:read|explain|show)\s+(?:the\s+)?(?:current|active)\s+file\b", cleaned_speech):
        return {"action": "read_active_file", "query": ""}
    if re.search(r"\banalyze\s+(?:the\s+)?(?:current|active)\s+code\b", cleaned_speech):
        return {"action": "analyze_code", "query": ""}

    # Rule YOUTUBE-SEARCH: Search YouTube or open something on YouTube
    # 1. "open youtube and search for X" or "search youtube for X"
    m_yt1 = re.search(r"\b(?:open\s+(?:youtube|yt)\s+(?:and\s+)?search(?:\s+for)?|search\s+(?:on\s+)?(?:youtube|yt)\s+(?:for)?)\s+(.+)", orig_speech, flags=re.IGNORECASE)
    if m_yt1:
        q_yt = m_yt1.group(1).strip(".?!,;\"' ")
        return {"action": "youtube_search", "query": q_yt}

    # 2. "search for X on/in youtube" or "search X on/in youtube"
    m_yt2 = re.search(r"\bsearch\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+(?:youtube|yt)\b", orig_speech, flags=re.IGNORECASE)
    if m_yt2:
        q_yt = m_yt2.group(1).strip(".?!,;\"' ")
        return {"action": "youtube_search", "query": q_yt}

    # 3. "open X on/in youtube" (e.g. "open the channel on YouTube", "open Mr Beast on YouTube", "open MKBHD on YouTube")
    m_yt3 = re.search(r"\bopen\s+(.+?)\s+(?:on|in)\s+(?:youtube|yt)\b", orig_speech, flags=re.IGNORECASE)
    if m_yt3:
        target_yt = m_yt3.group(1).strip(".?!,;\"' ")
        if target_yt.lower() in {"the channel", "channel", "his channel", "her channel", "their channel", "that channel"}:
            for turn in reversed(_CONVERSATION_TURNS):
                q_prev = turn.get("query")
                if q_prev and q_prev.lower() not in {"the channel", "channel", "local", "here"}:
                    target_yt = f"{q_prev} channel"
                    break
        return {"action": "youtube_search", "query": target_yt}

    # Rule PLAY: Play song/music on YouTube or Spotify (evaluated before generic open_app!)
    play_match = re.search(r"\b(?:open\s+(?:youtube|yt)\s+(?:and\s+)?play|open\s+spotify\s+(?:and\s+)?play|play)\s+(.+)", orig_speech, flags=re.IGNORECASE)
    if play_match:
        target_song = play_match.group(1).strip()
        target_song = re.sub(r"^(?:the\s+)?(?:song|video|track)\s+", "", target_song, flags=re.IGNORECASE).strip()
        target_song = target_song.strip(".?!,;\"' ")

        # Check platform preference
        if re.search(r"\s+(?:on|in|using)\s+spotify$", target_song, flags=re.IGNORECASE) or "spotify" in cleaned_speech:
            song_name = re.sub(r"\s+(?:on|in|using)\s+spotify$", "", target_song, flags=re.IGNORECASE).strip(".?!,;\"' ")
            if song_name.lower() in {"it", "that", "that song", ""}:
                for turn in reversed(_CONVERSATION_TURNS):
                    if turn.get("role") == "assistant":
                        try:
                            prev = json.loads(turn.get("content", "{}"))
                            if prev.get("query"):
                                song_name = prev["query"]
                                break
                        except Exception:
                            pass
            return {"action": "spotify_play", "query": song_name if song_name else None}
        else:
            song_name = re.sub(r"\s+(?:on|in|using)\s+(?:youtube|yt)$", "", target_song, flags=re.IGNORECASE).strip(".?!,;\"' ")
            return {"action": "youtube_play", "query": song_name if song_name else None}

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
        # Guard: Never treat folders, directories, files, or documents as applications!
        if re.search(r"\b(?:folder|directory|file|documents?)\b", target, flags=re.IGNORECASE):
            return None
        if target in {"spotify"}:
            return {"action": "spotify_open"}
        if target in {"youtube", "yt", "google"}:
            return {"action": "open_website", "query": target}
        if target:
            return {"action": "open_app", "query": target.title()}

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


SYNTHESIS_SYSTEM_PROMPT = """You are the voice reasoning layer of DeskBot, an intelligent Windows voice assistant.

Your task is to synthesize raw web search results into a concise, natural, spoken answer for the user.
The answer will be spoken aloud to the user using text-to-speech.

Guidelines:
1. Synthesize the facts, dates, sources, and developments into 2 to 4 natural, spoken sentences.
2. DO NOT say "Here is what I found for..." or read raw snippets or cite full URLs.
3. Speak naturally and authoritatively like an intelligent assistant (e.g., "According to recent reports...", "In recent developments...").
4. If the search results do NOT contain enough information to confirm the user's specific question or event, be honest:
   For example: "I couldn't find a reliable source confirming a major event happening right now."
   DO NOT fabricate facts or hallucinate details not grounded in the search results.
5. Keep the language clear, conversational, and direct for audio delivery.
6. Never say you cannot open YouTube or control the computer; DeskBot has native computer tools to open and control YouTube.
"""


def _update_last_assistant_turn(user_query: str, search_query: str, answer: str) -> None:
    """Update or append turn history with synthesized answer for seamless follow-up reasoning."""
    if _CONVERSATION_TURNS and _CONVERSATION_TURNS[-1].get("role") == "assistant":
        try:
            prev = json.loads(_CONVERSATION_TURNS[-1]["content"])
            if isinstance(prev, dict) and prev.get("action") == "web_search":
                prev["answer"] = answer
                _CONVERSATION_TURNS[-1]["content"] = json.dumps(prev)
                return
        except Exception:
            pass
        _CONVERSATION_TURNS[-1]["content"] = answer
    else:
        _CONVERSATION_TURNS.append({"role": "user", "content": user_query})
        _CONVERSATION_TURNS.append({"role": "assistant", "content": answer})


def synthesize_web_answer(
    user_query: str,
    search_query: str,
    results: list[dict[str, Any]],
    context_prompt: str = "",
) -> str:
    """Synthesize live search results into a concise, natural, spoken answer (2-4 sentences).

    Separates information retrieval from answer generation: analyzes facts, dates,
    sources, and developments into voice-ready text-to-speech phrasing.
    """
    if not results:
        return f"I searched for '{search_query}', but couldn't find any relevant web results."

    # Format search results cleanly for the LLM
    formatted_results = []
    for i, r in enumerate(results[:4], 1):
        title = r.get("title", f"Result {i}").strip()
        snippet = r.get("snippet", "").strip()
        url = r.get("url", "").strip()
        formatted_results.append(f"[{i}] {title}\nSummary: {snippet}\nSource URL: {url}")
    search_content = "\n\n".join(formatted_results)

    user_prompt = f"""User Question: "{user_query}"
Search Query: "{search_query}"

Search Results:
{search_content}

Synthesize a 2-4 sentence spoken answer based strictly on the search results above."""

    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        # Graceful offline fallback: extract top snippets cleanly
        top = results[0]
        top_title = top.get("title", "")
        top_snippet = top.get("snippet", "")
        if top_title and top_snippet:
            return f"According to {top_title}: {top_snippet}"
        elif top_snippet:
            return top_snippet
        return f"Found results for '{search_query}', but could not generate a summary."

    try:
        client = create_client()
        messages = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        ]
        if context_prompt:
            messages.append({"role": "system", "content": f"Recent Conversation Context:\n{context_prompt}"})

        messages.append({"role": "user", "content": user_prompt})

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=300,
        )

        synthesized = response.choices[0].message.content
        if synthesized and synthesized.strip():
            answer = synthesized.strip()
            # Update conversational turn history with the synthesized spoken answer
            _update_last_assistant_turn(user_query, search_query, answer)
            return answer

    except Exception as error:
        logger.warning("Answer synthesis failed: %s", error)

    # Fallback if synthesis call errors
    top = results[0]
    top_title = top.get("title", "")
    top_snippet = top.get("snippet", "")
    if top_title and top_snippet:
        return f"According to {top_title}: {top_snippet}"
    return top_snippet or f"Here is what I found for '{search_query}'."


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