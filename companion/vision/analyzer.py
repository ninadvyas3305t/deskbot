"""Vision analyzer implementations using NVIDIA NIM multimodal vision models."""

from __future__ import annotations

import abc
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI

try:
    import config
except ImportError:
    from companion import config

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

VISION_SYSTEM_PROMPT = """You are the Visual Screen Intelligence layer for DeskBot, an AI voice companion.
Your job is to visually inspect the screenshot of the user's screen and understand whatever code, terminal output, UI, or technical content is visible.

KEY PRINCIPLES:
1. Screen pixels are your sole source of truth. You do NOT have or need local file access. The code may be inside VS Code, a browser, a terminal, a YouTube tutorial video, a PDF, or documentation.
2. Semantic Understanding: Don't just perform OCR. Understand what the code does, the programming language, key functions/classes, algorithmic logic, and data flow.
3. Errors & Tracebacks: If an error, stack trace, or syntax issue is visible, identify the root cause directly.
4. Video Tutorial Context: If the screen shows a video tutorial (e.g. YouTube), explain what the presenter is writing, demonstrating, or teaching.
5. Honesty & Uncertainty: If code is partially cut off, truncated by window borders, or low resolution, acknowledge what is clearly visible and what is uncertain. NEVER hallucinate unseen lines.
6. Spoken Response: Provide a concise, 2 to 4 sentence spoken response ready for text-to-speech. Do NOT use markdown asterisks (*, **), bullet points, or code fences in the spoken_response field. Make it sound natural when read aloud.

You must respond with EXACTLY ONE JSON object matching this schema:
{
  "content_type": "code" | "terminal_error" | "video_tutorial" | "documentation" | "web_page" | "mixed" | "other",
  "language": "<programming language name or 'unknown'>",
  "readability": "clear" | "partial" | "blurry" | "obscured",
  "summary": "<1-2 sentence technical summary of visible content>",
  "code_details": "<functions, classes, logic, or algorithms identified>",
  "visible_issues": "<any errors, tracebacks, syntax issues, or bugs visible, or 'none'>",
  "uncertainties": "<any truncated or unreadable sections, or 'none'>",
  "spoken_response": "<2-4 natural conversational sentences answering the user query for audio TTS>"
}
"""


@dataclass
class VisionAnalysis:
    """Structured result of visual screen intelligence analysis."""
    content_type: str = "other"
    language: str = "unknown"
    readability: str = "clear"
    summary: str = ""
    code_details: str = ""
    visible_issues: str = "none"
    uncertainties: str = "none"
    spoken_response: str = ""
    raw_model_response: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_type": self.content_type,
            "language": self.language,
            "readability": self.readability,
            "summary": self.summary,
            "code_details": self.code_details,
            "visible_issues": self.visible_issues,
            "uncertainties": self.uncertainties,
            "spoken_response": self.spoken_response,
            "metadata": self.metadata,
        }


class VisionAnalyzer(abc.ABC):
    """Abstract interface for screen vision analysis."""

    @abc.abstractmethod
    def analyze(
        self,
        image_data_uri: str,
        user_query: str = "",
        window_context: Optional[Dict[str, Any]] = None,
    ) -> VisionAnalysis:
        """Analyze a screen capture image with an optional user query and window context."""
        pass


def _fix_concatenated_words(text: str) -> str:
    """Split common fused preposition/pronoun/determiner token concatenation artifacts."""
    if not text:
        return ""
    pattern = re.compile(
        r"\b(on|in|of|at|to|for|with|from|by|about|under|over)"
        r"(your|the|this|that|these|those|my|our)\b",
        re.IGNORECASE,
    )
    def repl(m: re.Match) -> str:
        w1, w2 = m.group(1), m.group(2)
        return f"{w1} {w2}"

    cleaned = pattern.sub(repl, text)

    aux_pattern = re.compile(
        r"\b(is|are|was|were)(currently|showing|displaying|running)\b",
        re.IGNORECASE,
    )
    cleaned = aux_pattern.sub(lambda m: f"{m.group(1)} {m.group(2)}", cleaned)

    subj_pattern = re.compile(
        r"\b(you|they|we)(are|have|can|will)\b",
        re.IGNORECASE,
    )
    cleaned = subj_pattern.sub(lambda m: f"{m.group(1)} {m.group(2)}", cleaned)
    return cleaned


def _deduplicate_consecutive_sentences(text: str) -> str:
    """Remove consecutive duplicate sentences that can occur during LLM completion."""
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) <= 1:
        return text

    deduped: List[str] = []
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        if deduped and s_clean.lower().rstrip(".!?") == deduped[-1].strip().lower().rstrip(".!?"):
            continue
        deduped.append(s_clean)
    return " ".join(deduped)


def _clean_tts_text(text: str) -> str:
    """Clean markdown artifacts, token fusion typos, and metadata from text so it sounds natural when spoken."""
    if not text:
        return ""
    # Strip markdown bold/italics
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"[`]+", "", cleaned)
    cleaned = re.sub(r"(?:^|\s)#+\s*", " ", cleaned)

    # Strip leading field labels if any leaked into the text
    cleaned = re.sub(
        r"^(?:spoken[ _\-]?response|summary|answer)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Strip conversational filler prefixes
    cleaned = re.sub(
        r"^(?:answer:\s*|sure,?\s*(?:i\s+can\s+help\s+(?:you\s+)?with\s+that\.?\s*|here\s+(?:is|are)[^.:]*[:.]\s*)?|certainly!?,?\s*|based\s+on\s+(?:the\s+)?(?:screen(?:shot)?|image)[^.:]*[:.]\s*|in\s+(?:this\s+)?(?:image|screenshot)[^.:]*[:.]\s*)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Strip quotation marks (including curly/smart quotes)
    cleaned = cleaned.strip("\"'“”‘’").strip()

    # Fix word/token concatenation artifacts (e.g. 'onyour' -> 'on your')
    cleaned = _fix_concatenated_words(cleaned)

    # Remove consecutive duplicate sentences
    cleaned = _deduplicate_consecutive_sentences(cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _normalize_key(raw_k: str) -> Optional[str]:
    """Map arbitrary field names from model text to canonical VisionAnalysis keys."""
    k = raw_k.lower().replace("-", " ").replace("_", " ").strip()
    if "spoken" in k or "speech" in k or "voice" in k or k == "answer":
        return "spoken_response"
    if "summary" in k:
        return "summary"
    if "code" in k or "detail" in k:
        return "code_details"
    if "issue" in k or "error" in k or "bug" in k:
        return "visible_issues"
    if "uncertain" in k:
        return "uncertainties"
    if "content" in k:
        return "content_type"
    if "lang" in k:
        return "language"
    if "readab" in k:
        return "readability"
    return None


def _parse_key_value_blocks(text: str) -> Dict[str, str]:
    """Parse key-value / YAML-style formatted text into a canonical field dictionary."""
    fields: Dict[str, List[str]] = {}
    current_key: Optional[str] = None

    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        clean_line = trimmed.replace("**", "").replace("__", "")
        unmarked = re.sub(r"^[-*#>\s]+", "", clean_line).strip()

        # Check for Key: Value (e.g. Content Type: mixed, Spoken Response: "...")
        m_field = re.match(r"^([a-zA-Z _\-]+)\s*[:=\-]\s*(.*)$", unmarked)
        if m_field:
            norm_k = _normalize_key(m_field.group(1))
            if norm_k:
                current_key = norm_k
                if norm_k not in fields:
                    fields[norm_k] = []
                val = m_field.group(2).strip()
                if val:
                    fields[norm_k].append(val)
                continue

        # Check for Header Only (e.g. "### Spoken Response" or "Summary:")
        m_hdr = re.match(r"^([a-zA-Z _\-]+)\s*[:?]?$", unmarked)
        if m_hdr:
            norm_k = _normalize_key(m_hdr.group(1))
            if norm_k:
                current_key = norm_k
                if norm_k not in fields:
                    fields[norm_k] = []
                continue

        if current_key:
            fields[current_key].append(trimmed)

    result: Dict[str, str] = {}
    for k, lines in fields.items():
        combined = " ".join(lines).strip()
        combined = combined.strip("\"'“”‘’").strip()
        result[k] = combined

    return result


def _parse_vision_response(raw_text: str, user_query: str = "") -> VisionAnalysis:
    """Parse JSON or key-value response from vision model, with robust fallback extractors."""
    clean_text = raw_text.strip()
    clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\s*```$", "", clean_text)

    # 1. Direct JSON parse
    try:
        data = json.loads(clean_text)
        if isinstance(data, dict):
            spoken = _clean_tts_text(str(data.get("spoken_response", "")).strip())
            if not spoken:
                spoken = _clean_tts_text(str(data.get("summary", "")).strip())
            return VisionAnalysis(
                content_type=str(data.get("content_type", "code")),
                language=str(data.get("language", "unknown")),
                readability=str(data.get("readability", "clear")),
                summary=str(data.get("summary", "")),
                code_details=str(data.get("code_details", "")),
                visible_issues=str(data.get("visible_issues", "none")),
                uncertainties=str(data.get("uncertainties", "none")),
                spoken_response=spoken or "I analyzed the code on your screen.",
                raw_model_response=raw_text,
            )
    except Exception:
        pass

    # 2. Substring JSON search
    match = re.search(r"\{[\s\S]*\}", clean_text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                spoken = _clean_tts_text(str(data.get("spoken_response", "")).strip())
                if not spoken:
                    spoken = _clean_tts_text(str(data.get("summary", "")).strip())
                return VisionAnalysis(
                    content_type=str(data.get("content_type", "code")),
                    language=str(data.get("language", "unknown")),
                    readability=str(data.get("readability", "clear")),
                    summary=str(data.get("summary", "")),
                    code_details=str(data.get("code_details", "")),
                    visible_issues=str(data.get("visible_issues", "none")),
                    uncertainties=str(data.get("uncertainties", "none")),
                    spoken_response=spoken or "I analyzed the code on your screen.",
                    raw_model_response=raw_text,
                )
        except Exception:
            pass

    # 3. Key-Value / YAML-style parsing (e.g. Llama 3.2 Vision returning structured keys)
    kv_fields = _parse_key_value_blocks(clean_text)
    if kv_fields and ("spoken_response" in kv_fields or "summary" in kv_fields or "content_type" in kv_fields):
        spoken_raw = kv_fields.get("spoken_response", "")
        summary_raw = kv_fields.get("summary", "")
        spoken = _clean_tts_text(spoken_raw)
        if not spoken:
            spoken = _clean_tts_text(summary_raw)
        summary = summary_raw or spoken

        detected_lang = kv_fields.get("language", "unknown")
        if detected_lang.lower() in ("unknown", "none", "n/a"):
            for cand in ("python", "javascript", "typescript", "c++", "cpp", "rust", "golang", "java", "html", "css", "bash", "swift", "kotlin", "sql"):
                if re.search(rf"\b{cand}\b", clean_text, flags=re.IGNORECASE):
                    detected_lang = cand
                    break

        return VisionAnalysis(
            content_type=kv_fields.get("content_type", "mixed"),
            language=detected_lang,
            readability=kv_fields.get("readability", "clear"),
            summary=summary,
            code_details=kv_fields.get("code_details", ""),
            visible_issues=kv_fields.get("visible_issues", "none"),
            uncertainties=kv_fields.get("uncertainties", "none"),
            spoken_response=spoken or "I analyzed your screen.",
            raw_model_response=raw_text,
        )

    # 4. Plaintext fallback if model returned conversational text instead of structured format
    clean_lines = []
    meta_line_pattern = re.compile(
        r"^(?:[-*#>\s]*)"
        r"(content[ _\-]?type|language|programming[ _\-]?language|readability|code[ _\-]?details|visible[ _\-]?issues|uncertainties|uncertainty)"
        r"\s*[:=\-]",
        re.IGNORECASE,
    )
    for line in clean_text.splitlines():
        if meta_line_pattern.match(line.strip().replace("**", "").replace("__", "")):
            continue
        clean_lines.append(line)
    sanitized_text = "\n".join(clean_lines)

    spoken_fallback = _clean_tts_text(sanitized_text)

    # Heuristic language extraction
    detected_lang = "unknown"
    if re.search(r"(?:^|[\s(])c\+\+(?:$|[\s),.;:])", clean_text, flags=re.IGNORECASE):
        detected_lang = "c++"
    else:
        for cand in ("python", "javascript", "typescript", "cpp", "rust", "golang", "java", "html", "css", "bash", "swift", "kotlin", "sql"):
            if re.search(rf"\b{cand}\b", clean_text, flags=re.IGNORECASE):
                detected_lang = cand
                break

    # Heuristic content type
    lower_text = clean_text.lower()
    if any(k in lower_text for k in ("error", "traceback", "exception", "failed", "crash")):
        c_type = "terminal_error"
    elif any(k in lower_text for k in ("video", "tutorial", "presenter", "youtube")):
        c_type = "video_tutorial"
    elif any(k in lower_text for k in ("function", "class", "code", "syntax", "def ", "return", "import")):
        c_type = "code"
    else:
        c_type = "mixed"

    return VisionAnalysis(
        content_type=c_type,
        language=detected_lang,
        readability="clear",
        summary=spoken_fallback[:200],
        code_details=spoken_fallback,
        visible_issues="none",
        uncertainties="none",
        spoken_response=spoken_fallback if spoken_fallback else "I examined your screen.",
        raw_model_response=raw_text,
    )



class NvidiaVisionAnalyzer(VisionAnalyzer):
    """Vision analyzer powered by NVIDIA NIM multimodal models."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: str = NVIDIA_BASE_URL,
    ):
        self.model = model or config.DEFAULT_VISION_MODEL
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            try:
                from platform_layer.credentials import get_credential_store
                self.api_key = get_credential_store().get_api_key()
            except Exception:
                try:
                    from companion.platform_layer.credentials import get_credential_store
                    self.api_key = get_credential_store().get_api_key()
                except Exception:
                    pass
        self.base_url = base_url

    def _create_client(self) -> OpenAI:
        if not self.api_key:
            try:
                from platform_layer.credentials import get_credential_store
                self.api_key = get_credential_store().get_api_key()
            except Exception:
                pass
        if not self.api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY is not set. Screen vision intelligence requires an NVIDIA API key."
            )
        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=25.0,
        )

    def analyze(
        self,
        image_data_uri: str,
        user_query: str = "",
        window_context: Optional[Dict[str, Any]] = None,
    ) -> VisionAnalysis:
        """Call NVIDIA multimodal API with screen image and prompt."""
        client = self._create_client()

        # Build prompt incorporating user query and auxiliary window context
        query_text = user_query.strip() if user_query else "What is on my screen? Explain the code or technical content visible."

        context_hint = ""
        if window_context:
            app = window_context.get("application", "")
            title = window_context.get("title", "")
            if app or title:
                context_hint = f"\n[System Context: Active Foreground Application: '{app}', Window Title: '{title}']\n"

        prompt_text = (
            f"{context_hint}"
            f"User Question: \"{query_text}\"\n\n"
            f"Carefully examine the screen image above. Identify the visible code, programming language, "
            f"logic, error tracebacks, or tutorial explanations. Answer the user's question directly in spoken_response. "
            f"Ensure spoken_response is 2 to 4 natural sentences suitable for text-to-speech."
        )

        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_uri,
                        },
                    },
                ],
            },
        ]

        logger.info("Sending screen capture to vision model: %s", self.model)
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=450,
            )
            raw_content = response.choices[0].message.content or ""
        except Exception as primary_err:
            logger.warning("Vision model %s failed: %s", self.model, primary_err)
            raise primary_err

        analysis = _parse_vision_response(raw_content, user_query=user_query)
        if window_context:
            analysis.metadata["window_context"] = window_context
        analysis.metadata["model"] = self.model
        return analysis



class MockVisionAnalyzer(VisionAnalyzer):
    """Deterministic mock analyzer for unit tests and offline testing."""

    def __init__(self, predefined_response: Optional[VisionAnalysis] = None):
        self.predefined_response = predefined_response or VisionAnalysis(
            content_type="code",
            language="python",
            readability="clear",
            summary="Python script implementing binary search algorithm.",
            code_details="Defines binary_search(arr, target) using low, high pointers and while loop.",
            visible_issues="none",
            uncertainties="none",
            spoken_response="On your screen, you have a Python implementation of binary search. It checks if the target exists in a sorted array in logarithmic time.",
        )
        self.calls: List[Dict[str, Any]] = []

    def analyze(
        self,
        image_data_uri: str,
        user_query: str = "",
        window_context: Optional[Dict[str, Any]] = None,
    ) -> VisionAnalysis:
        self.calls.append({
            "image_len": len(image_data_uri),
            "user_query": user_query,
            "window_context": window_context,
        })
        return self.predefined_response
