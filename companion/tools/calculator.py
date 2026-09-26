"""Safe, deterministic mathematical calculation engine for DeskBot.

Evaluates arithmetic, square roots, percentages, and basic equations using AST parsing.
Zero arbitrary code execution, zero eval(), and zero shell calls.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any, Dict, Optional, Tuple

# Supported binary operators
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Supported unary operators
_SAFE_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Allowed math functions and constants
_SAFE_FUNCTIONS: Dict[str, Any] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "pi": math.pi,
    "e": math.e,
}


def _eval_ast(node: ast.AST) -> float | int:
    """Recursively evaluate an AST node safely."""
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)

    if isinstance(node, ast.Constant):  # Python 3.8+
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type}")
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")
        if op_type == ast.Pow and (abs(right) > 1000 or abs(left) > 100000):
            raise OverflowError("Exponent too large to compute safely")
        return _SAFE_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_UNARY_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type}")
        operand = _eval_ast(node.operand)
        return _SAFE_UNARY_OPERATORS[op_type](operand)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct function calls are allowed")
        func_name = node.func.id
        if func_name not in _SAFE_FUNCTIONS or not callable(_SAFE_FUNCTIONS[func_name]):
            raise ValueError(f"Function '{func_name}' is not allowed")
        args = [_eval_ast(arg) for arg in node.args]
        return _SAFE_FUNCTIONS[func_name](*args)

    if isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCTIONS and not callable(_SAFE_FUNCTIONS[node.id]):
            return _SAFE_FUNCTIONS[node.id]
        raise ValueError(f"Variable or function '{node.id}' is not recognized")

    raise ValueError(f"Unsupported syntax tree element: {type(node)}")


def solve_simple_linear_equation(query: str) -> Optional[str]:
    """Solve simple linear equations of the form ax + b = c or ax = b."""
    clean = query.strip()
    if "=" not in clean:
        return None

    # Normalization: e.g. "solve 2x + 5 = 15" -> "2x + 5 = 15"
    clean = re.sub(r"^(?:solve|calculate|what\s+is)\s+", "", clean, flags=re.IGNORECASE).strip()

    pattern = r"^\s*([+-]?\s*\d*\.?\d*)\s*([a-zA-Z])\s*([+-]\s*\d+\.?\d*)?\s*=\s*([+-]?\s*\d+\.?\d*)\s*$"
    m = re.match(pattern, clean)
    if not m:
        return None

    a_str, var_name, b_str, c_str = m.groups()

    if not a_str or a_str.strip() in ("", "+"):
        a = 1.0
    elif a_str.strip() == "-":
        a = -1.0
    else:
        a = float(a_str.replace(" ", ""))

    if a == 0:
        return None

    b = 0.0
    if b_str:
        b = float(b_str.replace(" ", ""))

    c = float(c_str.replace(" ", ""))

    x = (c - b) / a
    ans_val = int(x) if x.is_integer() else round(x, 4)
    return f"{var_name} = {ans_val}"


def format_number(val: float | int) -> str:
    """Format numeric result cleanly without unnecessary trailing decimals."""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    if isinstance(val, float):
        r = round(val, 6)
        if r.is_integer():
            return str(int(r))
        return f"{r:.6f}".rstrip("0").rstrip(".")
    return str(val)


def evaluate_math(query: str) -> Optional[str]:
    """Deterministically parse and evaluate natural language math queries.

    Returns a clean, user-friendly spoken response string, or None if not a math query.
    """
    if not query or not query.strip():
        return None

    text = query.strip()

    # 1. Linear equation check
    if "=" in text:
        eq_sol = solve_simple_linear_equation(text)
        if eq_sol:
            return eq_sol

    # 2. Percentage check: e.g. "15% of 200", "17.5 percent of 800"
    pct_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:%|\s*percent)\s+of\s+(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if pct_match:
        pct = float(pct_match.group(1))
        base = float(pct_match.group(2))
        res = (pct / 100.0) * base
        return f"{format_number(pct)}% of {format_number(base)} is {format_number(res)}."

    # 3. Square root check: "square root of 64", "sqrt(144)"
    sqrt_match = re.search(
        r"(?:square\s*root\s*(?:of)?|sqrt\s*(?:\(?))\s*(\d+(?:\.\d+)?)\)?",
        text,
        re.IGNORECASE,
    )
    if sqrt_match:
        val = float(sqrt_match.group(1))
        if val < 0:
            return "The square root of a negative number is not a real number."
        res = math.sqrt(val)
        return f"The square root of {format_number(val)} is {format_number(res)}."

    # 4. Arithmetic translation:
    cleaned = text
    cleaned = re.sub(r"^(?:what\s*(?:'s|\s+is)|\s*calculate|\s*compute|\s*evaluate)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[?!.,;]+$", "", cleaned).strip()

    # Map spoken words to operators
    cleaned = re.sub(r"\b(?:times|multiplied\s+by)\b", "*", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:divided\s+by|over)\b", "/", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bplus\b", "+", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bminus\b", "-", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bto\s+the\s+power\s+of\b", "**", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\^", "**", cleaned)
    cleaned = re.sub(r"\bx\b", "*", cleaned, flags=re.IGNORECASE)

    # Must contain at least one digit and an operator
    if not re.search(r"\d", cleaned) or not re.search(r"[+\-*/%*]", cleaned):
        return None

    # Filter out sentences that have non-math words remaining
    stripped = re.sub(r"[0-9+\-*/().\s,eE]", "", cleaned)
    if stripped:
        allowed_letters = set("sqrtabsroundfloorceilsinscotanlogpi")
        if not set(stripped.lower()).issubset(allowed_letters):
            return None

    try:
        parsed_ast = ast.parse(cleaned, mode="eval")
        result = _eval_ast(parsed_ast)
        ans_str = format_number(result)

        # Build natural spoken sentence if query is simple arithmetic
        mult_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\*|times|multiplied\s+by)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if mult_m:
            return f"{mult_m.group(1)} multiplied by {mult_m.group(2)} is {ans_str}."

        div_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:/|divided\s+by)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if div_m:
            return f"{div_m.group(1)} divided by {div_m.group(2)} is {ans_str}."

        add_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|plus)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if add_m:
            return f"{add_m.group(1)} plus {add_m.group(2)} is {ans_str}."

        sub_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|minus)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if sub_m:
            return f"{sub_m.group(1)} minus {sub_m.group(2)} is {ans_str}."

        return f"{ans_str}"
    except Exception:
        return None
