"""Safe, deterministic Windows File Explorer, filesystem, and VS Code operations for DeskBot.

Enforces strict path safety:
- Never executes arbitrary shell strings.
- Uses controlled workspace root without traversing the entire drive.
- Prevents tampering with sensitive system directories.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from command_executor import ToolResult

logger = logging.getLogger(__name__)

# Standard safe user directories
STANDARD_DIRECTORIES: Dict[str, Path] = {
    "desktop": Path.home() / "Desktop",
    "downloads": Path.home() / "Downloads",
    "documents": Path.home() / "Documents",
    "pictures": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
    "projects": Path.home() / "Projects",
    "deskbot": config.WORKSPACE_ROOT,
}

# Forbidden directories that must never be created/modified
FORBIDDEN_ROOTS = [
    Path(os.environ.get("SystemRoot", "C:/Windows")).resolve(),
    Path(os.environ.get("ProgramFiles", "C:/Program Files")).resolve(),
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")).resolve(),
    Path("C:/").resolve(),
]


def is_path_safe(p: Path) -> bool:
    """Verify that a path does not target sensitive system roots."""
    try:
        resolved = p.resolve()
        for forbidden in FORBIDDEN_ROOTS:
            if resolved == forbidden or (forbidden != Path("C:/").resolve() and forbidden in resolved.parents):
                return False
        return True
    except Exception:
        return False


def find_file_in_workspace(filename: str, max_depth: int = 3) -> Optional[Path]:
    """Search for a specific file within the configured workspace root without scanning C: drive."""
    clean_target = filename.strip().lower()
    root = config.WORKSPACE_ROOT.resolve()

    if not root.is_dir():
        return None

    # Check direct match first
    direct = root / clean_target
    if direct.is_file():
        return direct

    # Breadth-first / limited depth search
    skip_dirs = {".git", ".pio", "__pycache__", "node_modules", ".vscode", "venv", ".penv"}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        rel_depth = len(Path(dirpath).relative_to(root).parts)
        if rel_depth > max_depth:
            dirnames.clear()
            continue

        for f in filenames:
            if f.lower() == clean_target:
                return Path(dirpath) / f

    return None


def normalize_spoken_filename(spec: str) -> str:
    """Normalize common spoken STT patterns into standard filenames.

    Handles:
        'document dot txt' -> 'document.txt'
        'notes dot txt' -> 'notes.txt'
        'main dot py' -> 'main.py'
        'test dot py' -> 'test.py'
        'notes .txt' -> 'notes.txt'
        'notes.txt.' -> 'notes.txt'
    """
    clean = spec.strip()
    clean = clean.strip(".,?!;:`'\"")
    clean = re.sub(r"\s+dot\s+([a-zA-Z0-9]+)\b", r".\1", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bdot\s+([a-zA-Z0-9]+)\b", r".\1", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+\.([a-zA-Z0-9]+)\b", r".\1", clean)
    return clean.strip().strip(".,?!;:`'\"")


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def find_filename_candidates(target_name: str, search_dir: Path) -> List[Tuple[Path, float]]:
    """Search search_dir for candidate files matching target_name via fuzzy & phonetic similarity."""
    if not search_dir.is_dir():
        return []

    target_p = Path(target_name)
    target_stem = target_p.stem.lower()
    target_ext = target_p.suffix.lower()

    candidates: List[Tuple[Path, float]] = []

    try:
        for entry in search_dir.iterdir():
            if not entry.is_file():
                continue
            if entry.name.startswith((".", "~$", "$")):
                continue

            cand_stem = entry.stem.lower()
            cand_ext = entry.suffix.lower()

            ext_match = (target_ext == cand_ext) if target_ext else True

            stem_ratio = difflib.SequenceMatcher(None, target_stem, cand_stem).ratio()
            full_ratio = difflib.SequenceMatcher(None, target_name.lower(), entry.name.lower()).ratio()

            score = 0.0
            if ext_match and target_ext:
                score = stem_ratio * 0.8 + full_ratio * 0.2
            else:
                score = full_ratio * 0.6 + stem_ratio * 0.4

            edit_dist = _levenshtein_distance(target_stem, cand_stem)
            if edit_dist <= 1 and ext_match:
                score = max(score, 0.82)
            elif edit_dist <= 2 and len(target_stem) >= 4 and ext_match:
                score = max(score, 0.74)

            # Homophone and acoustic confusion pairs (e.g. nodes <-> notes, mane <-> main, text <-> test)
            confusion_pairs = {
                ("nodes", "notes"), ("notes", "nodes"),
                ("text", "test"), ("test", "text"),
                ("mane", "main"), ("main", "mane"),
                ("reed", "read"), ("read", "reed"),
                ("scrip", "script"), ("script", "scrip"),
                ("dock", "doc"), ("doc", "dock"),
                ("rite", "write"), ("write", "rite"),
            }
            if (target_stem, cand_stem) in confusion_pairs and ext_match:
                score = max(score, 0.90)

            if score >= 0.70:
                candidates.append((entry, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
    except Exception as err:
        logger.debug("Candidate search error in %s: %s", search_dir, err)

    return candidates


class ResolvedFileTarget:
    """Result of safe filename resolution with exact and fuzzy candidate reporting."""

    def __init__(
        self,
        requested_name: str,
        exact_match: Optional[Path] = None,
        candidates: Optional[List[Path]] = None,
        search_dir: Optional[Path] = None,
    ):
        self.requested_name = requested_name
        self.exact_match = exact_match
        self.candidates = candidates or []
        self.search_dir = search_dir or STANDARD_DIRECTORIES["desktop"]


def resolve_file_candidate(
    spec: str,
    allow_workspace: bool = True,
    default_to_desktop: bool = True,
) -> ResolvedFileTarget:
    """Deterministically resolve a file spec with exact match or ranked candidates."""
    clean = normalize_spoken_filename(spec)
    target_name, location_hint = parse_location_spec(clean)

    parent_dir: Optional[Path] = None
    if location_hint and location_hint in STANDARD_DIRECTORIES:
        parent_dir = STANDARD_DIRECTORIES[location_hint]

    # Check absolute path
    try:
        p_abs = Path(target_name)
        if p_abs.is_absolute():
            if p_abs.is_file() and is_path_safe(p_abs):
                print(f"[FILE] Requested filename: {target_name}", flush=True)
                print(f"[FILE] Exact match: {p_abs.name}", flush=True)
                return ResolvedFileTarget(target_name, exact_match=p_abs, search_dir=p_abs.parent)
            else:
                # Specified an explicit absolute path that does not exist or is not a file
                parent_dir = p_abs.parent if p_abs.parent.is_dir() else None
                target_name = p_abs.name
    except Exception:
        pass

    target_p = Path(target_name)
    is_code = target_p.suffix.lower() in {".py", ".cpp", ".c", ".h", ".json", ".toml", ".yaml", ".ini"}

    dirs_to_search: List[Path] = []
    if parent_dir:
        dirs_to_search.append(parent_dir)
    else:
        companion_dir = config.WORKSPACE_ROOT / "companion"
        if is_code and allow_workspace:
            dirs_to_search.append(config.WORKSPACE_ROOT)
            if companion_dir.is_dir():
                dirs_to_search.append(companion_dir)
            if default_to_desktop:
                dirs_to_search.append(STANDARD_DIRECTORIES["desktop"])
        else:
            if default_to_desktop:
                dirs_to_search.append(STANDARD_DIRECTORIES["desktop"])
            if allow_workspace:
                dirs_to_search.append(config.WORKSPACE_ROOT)
                if companion_dir.is_dir():
                    dirs_to_search.append(companion_dir)

    print(f"[FILE] Requested filename: {target_name}", flush=True)

    # 1. Exact match check
    for s_dir in dirs_to_search:
        exact_p = s_dir / target_name
        if exact_p.is_file() and is_path_safe(exact_p):
            print(f"[FILE] Exact match: {exact_p.name}", flush=True)
            return ResolvedFileTarget(target_name, exact_match=exact_p, search_dir=s_dir)

    if allow_workspace and config.WORKSPACE_ROOT in dirs_to_search:
        ws_exact = find_file_in_workspace(target_name)
        if ws_exact and ws_exact.is_file() and is_path_safe(ws_exact):
            print(f"[FILE] Exact match: {ws_exact.name}", flush=True)
            return ResolvedFileTarget(target_name, exact_match=ws_exact, search_dir=ws_exact.parent)

    print("[FILE] Exact match: none", flush=True)

    # 2. Candidate match check
    all_cands: List[Tuple[Path, float]] = []
    for s_dir in dirs_to_search:
        cands = find_filename_candidates(target_name, s_dir)
        all_cands.extend(cands)

    all_cands.sort(key=lambda x: x[1], reverse=True)
    unique_cands: List[Path] = []
    seen: set[str] = set()
    for p, _score in all_cands:
        r_str = str(p.resolve())
        if r_str not in seen:
            seen.add(r_str)
            unique_cands.append(p)

    if len(unique_cands) == 1:
        print(f"[FILE] Candidate match: {unique_cands[0].name}", flush=True)
    elif len(unique_cands) > 1:
        c_names = ", ".join(c.name for c in unique_cands)
        print(f"[FILE] Candidate match: multiple ({c_names})", flush=True)
    else:
        print("[FILE] Candidate match: none", flush=True)

    chosen_dir = dirs_to_search[0] if dirs_to_search else STANDARD_DIRECTORIES["desktop"]
    return ResolvedFileTarget(target_name, candidates=unique_cands, search_dir=chosen_dir)


def parse_location_spec(spec: str) -> Tuple[str, Optional[str]]:
    """Parse phrases like:
    - 'notes.txt on my Desktop'
    - 'on my desktop named notes.txt'
    - 'on my desktop called notes.txt'
    - 'in downloads called report.pdf'
    - 'on desktop notes.txt'

    Returns (target_name, location_hint).
    """
    clean = normalize_spoken_filename(spec)
    clean = re.sub(r"^(?:a\s+file\s+called|a\s+folder\s+called|file\s+called|folder\s+called|file|folder)\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(?:called|named)\s+", "", clean, flags=re.IGNORECASE).strip()

    # Pattern 1: Location first - "(?:on|in|inside)(?: my)? <location> (?:called |named )?<target>"
    m_loc_first = re.search(r"^(?:on|in|inside)(?:\s+my)?\s+([a-zA-Z0-9_\-]+)\s+(?:called\s+|named\s+)?(.+)$", clean, flags=re.IGNORECASE)
    if m_loc_first:
        loc_cand = m_loc_first.group(1).strip().lower()
        if loc_cand in STANDARD_DIRECTORIES:
            target = m_loc_first.group(2).strip()
            target = re.sub(r"^(?:called|named)\s+", "", target, flags=re.IGNORECASE).strip()
            return target, loc_cand

    # Pattern 2: Target first - "<target> (?:on|in|inside)(?: my)? <location>"
    m_target_first = re.search(r"^(.*?)\s+(?:on|in|inside)(?:\s+my)?\s+([a-zA-Z0-9_\- ]+)$", clean, flags=re.IGNORECASE)
    if m_target_first:
        target = m_target_first.group(1).strip()
        location = m_target_first.group(2).strip().lower()
        target = re.sub(r"^(?:called|named)\s+", "", target, flags=re.IGNORECASE).strip()
        return target, location

    return clean, None


def resolve_target_path(
    target_spec: str,
    allow_workspace_search: bool = True,
    default_to_desktop: bool = True,
) -> Optional[Path]:
    """Deterministically resolve a target string into a validated Path object."""
    if not target_spec or not target_spec.strip():
        return None

    raw_clean = target_spec.strip()

    # 1. Check if it's directly a standard folder keyword (e.g. "desktop", "downloads")
    lower_keyword = raw_clean.lower()
    if lower_keyword in STANDARD_DIRECTORIES:
        return STANDARD_DIRECTORIES[lower_keyword]

    # 2. Parse potential location hints (e.g. "notes.txt on Desktop", "Test inside Documents")
    target_name, location_hint = parse_location_spec(raw_clean)

    parent_dir: Optional[Path] = None
    if location_hint and location_hint in STANDARD_DIRECTORIES:
        parent_dir = STANDARD_DIRECTORIES[location_hint]

    # 3. Check if target_name is an existing absolute path
    try:
        p_cand = Path(target_name)
        if p_cand.is_absolute():
            return p_cand if is_path_safe(p_cand) else None
    except Exception:
        pass

    # 4. If a parent directory was specified, resolve within that directory
    if parent_dir:
        cand = (parent_dir / target_name).resolve()
        return cand if is_path_safe(cand) else None

    # 5. Search in workspace if requested (e.g. "main.py", "ai_brain.py")
    if allow_workspace_search:
        ws_file = find_file_in_workspace(target_name)
        if ws_file and is_path_safe(ws_file):
            return ws_file

    # 6. Default fallback location
    if default_to_desktop:
        desktop_target = (STANDARD_DIRECTORIES["desktop"] / target_name).resolve()
        if is_path_safe(desktop_target):
            return desktop_target

    return (config.WORKSPACE_ROOT / target_name).resolve()


# --- Deterministic Tool Operations ---

def open_file_explorer() -> ToolResult:
    """Launch Windows File Explorer."""
    try:
        subprocess.Popen(["explorer.exe"], shell=False)
        return ToolResult(True, "File Explorer opened", "Opening File Explorer.")
    except Exception as err:
        logger.error("Failed to open File Explorer: %s", err)
        return ToolResult(False, str(err), "Could not open File Explorer.")


def open_folder(folder_spec: str) -> ToolResult:
    """Open a validated folder in Windows Explorer."""
    clean = (folder_spec or "").strip()
    if not clean:
        return open_file_explorer()

    path = resolve_target_path(clean, allow_workspace_search=False, default_to_desktop=False)

    if not path or not path.exists():
        return ToolResult(False, f"Folder not found: {clean}", f"I couldn't find the folder '{clean}'.")

    if not path.is_dir():
        # If user asked to open folder on a file, open parent
        path = path.parent

    try:
        subprocess.Popen(["explorer.exe", str(path)], shell=False)
        folder_display = path.name if path.name else str(path)
        return ToolResult(True, f"Opened folder {path}", f"Opening {folder_display}.")
    except Exception as err:
        logger.error("Failed to open folder '%s': %s", path, err)
        return ToolResult(False, str(err), f"Could not open {path.name}.")


def create_file(file_spec: str, content: str = "") -> ToolResult:
    """Create a new file safely in a validated directory (defaults to Desktop)."""
    clean = (file_spec or "").strip()
    if not clean:
        return ToolResult(False, "Missing filename", "Please specify the name of the file to create.")

    target_path = resolve_target_path(clean, allow_workspace_search=False, default_to_desktop=True)
    if not target_path:
        return ToolResult(False, "Invalid path", "The requested file path is not allowed.")

    if not is_path_safe(target_path):
        return ToolResult(False, "Path forbidden", "Creating files in system directories is not allowed.")

    target_parent = target_path.parent
    if not target_parent.exists():
        try:
            target_parent.mkdir(parents=True, exist_ok=True)
        except Exception as err:
            return ToolResult(False, str(err), f"Could not create directory for {target_path.name}.")

    if target_path.exists():
        return ToolResult(True, f"File already exists: {target_path.name}", f"The file '{target_path.name}' already exists.")

    try:
        target_path.write_text(content, encoding="utf-8")
        location_desc = "on your Desktop" if target_parent == STANDARD_DIRECTORIES["desktop"] else f"in {target_parent.name}"
        return ToolResult(True, f"Created {target_path}", f"Created {target_path.name} {location_desc}.")
    except Exception as err:
        logger.error("Failed to create file '%s': %s", target_path, err)
        return ToolResult(False, str(err), f"Could not create {target_path.name}.")


def create_folder(folder_spec: str) -> ToolResult:
    """Create a new directory safely (defaults to Desktop if location unspecified)."""
    clean = (folder_spec or "").strip()
    if not clean:
        return ToolResult(False, "Missing folder name", "Please specify the name of the folder to create.")

    target_path = resolve_target_path(clean, allow_workspace_search=False, default_to_desktop=True)
    if not target_path:
        return ToolResult(False, "Invalid path", "The requested folder path is not allowed.")

    if not is_path_safe(target_path):
        return ToolResult(False, "Path forbidden", "Creating folders in system directories is not allowed.")

    if target_path.exists() and target_path.is_dir():
        return ToolResult(True, f"Folder already exists: {target_path.name}", "The folder already exists.")

    try:
        target_path.mkdir(parents=True, exist_ok=True)
        location_desc = "on your Desktop" if target_path.parent == STANDARD_DIRECTORIES["desktop"] else f"in {target_path.parent.name}"
        return ToolResult(True, f"Created folder {target_path}", f"Created folder {target_path.name} {location_desc}.")
    except Exception as err:
        logger.error("Failed to create folder '%s': %s", target_path, err)
        return ToolResult(False, str(err), f"Could not create folder {target_path.name}.")


def open_file(file_spec: str) -> ToolResult:
    """Open an existing file with its default Windows application, resolving strong candidates."""
    clean = (file_spec or "").strip()
    if not clean:
        return ToolResult(False, "Missing filename", "Please specify the file you would like to open.")

    res = resolve_file_candidate(clean, allow_workspace=True, default_to_desktop=True)

    target_path: Optional[Path] = None
    if res.exact_match:
        target_path = res.exact_match
    elif len(res.candidates) == 1:
        target_path = res.candidates[0]
        print(f"[FILE] Resolved candidate: {target_path.name}", flush=True)
    elif len(res.candidates) > 1:
        c_names = ", ".join(c.name for c in res.candidates[:4])
        return ToolResult(False, f"Multiple files found: {c_names}", f"I found multiple files: {c_names}. Which one would you like to open?")
    else:
        return ToolResult(False, f"File not found: {res.requested_name}", f"I couldn't find the file '{res.requested_name}'.")

    if not is_path_safe(target_path):
        return ToolResult(False, "Path forbidden", "Opening files in system directories is not allowed.")

    try:
        os.startfile(str(target_path))
        return ToolResult(True, f"Opened file {target_path}", f"Opening {target_path.name}.")
    except Exception as err:
        logger.error("Failed to open file '%s': %s", target_path, err)
        return ToolResult(False, str(err), f"Could not open {target_path.name}.")


def open_in_vscode(target_spec: str = "") -> ToolResult:
    """Launch VS Code opening the DeskBot workspace or a specific file/folder with candidate resolution."""
    clean = (target_spec or "").strip()

    # Default to opening the active project if no specific file/target requested
    if not clean or clean.lower() in ("deskbot", "project", "deskbot project", "codebase", "this folder", "workspace"):
        target_path = config.WORKSPACE_ROOT
    else:
        res = resolve_file_candidate(clean, allow_workspace=True, default_to_desktop=False)
        if res.exact_match:
            target_path = res.exact_match
        elif len(res.candidates) == 1:
            target_path = res.candidates[0]
            print(f"[FILE] Resolved candidate: {target_path.name}", flush=True)
        elif len(res.candidates) > 1:
            c_names = ", ".join(c.name for c in res.candidates[:4])
            return ToolResult(False, f"Multiple candidates: {c_names}", f"I found multiple files: {c_names}. Which one would you like to open in VS Code?")
        else:
            folder_p = resolve_target_path(clean, allow_workspace_search=False, default_to_desktop=False)
            if folder_p and folder_p.is_dir():
                target_path = folder_p
            else:
                return ToolResult(False, f"Target not found: {clean}", f"I couldn't find '{clean}' to open in VS Code.")

    if not is_path_safe(target_path):
        return ToolResult(False, "Path forbidden", "Opening paths in system directories is not allowed.")

    try:
        subprocess.Popen(["cmd", "/c", "code", str(target_path)], shell=False)
        display_name = target_path.name if target_path.name else str(target_path)
        return ToolResult(True, f"Opened {target_path} in VS Code", f"Opening {display_name} in VS Code.")
    except Exception as err:
        logger.error("Failed to launch VS Code for '%s': %s", target_path, err)
        return ToolResult(False, str(err), "Could not launch VS Code.")


def is_safe_to_delete(p: Path) -> bool:
    """Verify that a path is safe to delete and not a system directory or drive root."""
    try:
        resolved = p.resolve()
        if not is_path_safe(resolved):
            return False

        # Cannot delete drive roots (e.g. C:\, D:\)
        if len(resolved.parts) <= 1:
            return False

        # Cannot delete user profile root (e.g. C:\Users\Ninad)
        if resolved == Path.home().resolve():
            return False

        # Cannot delete the base standard directories themselves (e.g. Desktop, Downloads)
        for std_dir in STANDARD_DIRECTORIES.values():
            if resolved == std_dir.resolve():
                return False

        return True
    except Exception:
        return False


def delete_file(file_spec: str) -> ToolResult:
    """Delete a file safely with exact match deletion or candidate confirmation requirement."""
    clean = (file_spec or "").strip()
    if not clean:
        return ToolResult(False, "Missing filename", "Please specify the file you want to delete.")

    res = resolve_file_candidate(clean, allow_workspace=False, default_to_desktop=True)

    # 1. Exact match exists -> Delete directly
    if res.exact_match:
        target_path = res.exact_match
        if not is_safe_to_delete(target_path):
            return ToolResult(False, "Path protected", "Deleting system or root directories is not allowed.")
        if not target_path.is_file():
            return ToolResult(False, f"Not a file: {target_path.name}", f"'{target_path.name}' is a folder, not a file.")
        try:
            filename = target_path.name
            print(f"[FILE] Deleting: {filename}", flush=True)
            target_path.unlink()
            location_desc = "from your Desktop" if target_path.parent == STANDARD_DIRECTORIES["desktop"] else f"from {target_path.parent.name}"
            return ToolResult(True, f"Deleted {target_path}", f"Deleted {filename} {location_desc}.")
        except Exception as err:
            logger.error("Failed to delete file '%s': %s", target_path, err)
            return ToolResult(False, str(err), f"Could not delete {target_path.name}.")

    # 2. Candidate match found -> Require user confirmation (DO NOT delete yet)
    if len(res.candidates) == 1:
        cand = res.candidates[0]
        if not is_safe_to_delete(cand):
            return ToolResult(False, "Path protected", "Deleting system or root directories is not allowed.")
        prompt = f"I found {cand.name}. Do you want me to delete it?"
        print(f'[CONFIRMATION] Asking "{prompt}"', flush=True)
        return ToolResult(
            success=True,
            message=f"Confirmation required to delete {cand.name}",
            response_text=prompt,
            data={
                "confirmation_required": True,
                "action": "delete_file",
                "target_path": str(cand),
                "display_name": cand.name,
            },
        )

    # 3. Multiple candidates found -> Ask user to clarify
    if len(res.candidates) > 1:
        c_names = ", ".join(c.name for c in res.candidates[:4])
        prompt = f"I found multiple files: {c_names}. Which one do you want me to delete?"
        print(f'[CONFIRMATION] Asking "{prompt}"', flush=True)
        return ToolResult(
            success=False,
            message=f"Multiple candidate files: {c_names}",
            response_text=prompt,
            data={"ambiguous_candidates": [str(c) for c in res.candidates]},
        )

    # 4. No exact match and no candidates
    return ToolResult(
        False,
        f"File not found: {res.requested_name}",
        f"I couldn't find '{res.requested_name}' to delete.",
    )


def execute_pending_deletion(target_path_str: str) -> ToolResult:
    """Execute confirmed deletion of a candidate file."""
    try:
        p = Path(target_path_str)
        if not p.is_file():
            return ToolResult(False, f"File no longer exists: {p.name}", f"I couldn't find '{p.name}' to delete.")
        if not is_safe_to_delete(p):
            return ToolResult(False, "Path protected", "Deleting system or root directories is not allowed.")
        print(f"[FILE] Deleting: {p.name}", flush=True)
        p.unlink()
        location_desc = "from your Desktop" if p.parent == STANDARD_DIRECTORIES["desktop"] else f"from {p.parent.name}"
        return ToolResult(True, f"Deleted {p}", f"Deleted {p.name} {location_desc}.")
    except Exception as err:
        logger.error("Failed to delete '%s': %s", target_path_str, err)
        return ToolResult(False, str(err), f"Could not delete {p.name}.")


def delete_folder(folder_spec: str) -> ToolResult:
    """Delete a directory safely (only subdirectories inside safe locations)."""
    clean = (folder_spec or "").strip()
    if not clean:
        return ToolResult(False, "Missing folder name", "Please specify the folder you want to delete.")

    target_path = resolve_target_path(clean, allow_workspace_search=False, default_to_desktop=True)
    if not target_path:
        return ToolResult(False, "Invalid path", f"I couldn't resolve the path for '{clean}'.")

    if not is_safe_to_delete(target_path):
        return ToolResult(False, "Path protected", "Deleting protected or system directories is not allowed.")

    if not target_path.exists():
        return ToolResult(False, f"Folder not found: {clean}", f"I couldn't find '{clean}' to delete.")

    if not target_path.is_dir():
        return ToolResult(False, f"Not a folder: {clean}", f"'{clean}' is a file, not a folder.")

    try:
        dirname = target_path.name
        shutil.rmtree(target_path)
        location_desc = "from your Desktop" if target_path.parent == STANDARD_DIRECTORIES["desktop"] else f"from {target_path.parent.name}"
        return ToolResult(True, f"Deleted folder {target_path}", f"Deleted folder {dirname} {location_desc}.")
    except Exception as err:
        logger.error("Failed to delete folder '%s': %s", target_path, err)
        return ToolResult(False, str(err), f"Could not delete folder {target_path.name}.")
