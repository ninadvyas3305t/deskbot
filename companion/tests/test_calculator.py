"""Unit tests for safe deterministic calculator tool."""

import unittest
from companion.tools.calculator import (
    evaluate_math,
    format_number,
    solve_simple_linear_equation,
)


class TestCalculator(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(evaluate_math("What is 25 times 16?"), "25 multiplied by 16 is 400.")
        self.assertEqual(evaluate_math("100 divided by 4"), "100 divided by 4 is 25.")
        self.assertEqual(evaluate_math("50 plus 25"), "50 plus 25 is 75.")
        self.assertEqual(evaluate_math("100 minus 30"), "100 minus 30 is 70.")
        self.assertEqual(evaluate_math("2 to the power of 8"), "256")
        self.assertEqual(evaluate_math("3 ^ 4"), "81")

    def test_square_root(self):
        self.assertEqual(evaluate_math("What is the square root of 64?"), "The square root of 64 is 8.")
        self.assertEqual(evaluate_math("sqrt(144)"), "The square root of 144 is 12.")
        self.assertEqual(evaluate_math("square root of 0"), "The square root of 0 is 0.")

    def test_percentages(self):
        self.assertEqual(evaluate_math("Calculate 17.5% of 800"), "17.5% of 800 is 140.")
        self.assertEqual(evaluate_math("What is 15% of 200?"), "15% of 200 is 30.")
        self.assertEqual(evaluate_math("20 percent of 50"), "20% of 50 is 10.")

    def test_linear_equations(self):
        self.assertEqual(solve_simple_linear_equation("Solve 2x + 5 = 15"), "x = 5")
        self.assertEqual(solve_simple_linear_equation("3x - 9 = 0"), "x = 3")
        self.assertEqual(solve_simple_linear_equation("x + 10 = 25"), "x = 15")
        self.assertEqual(evaluate_math("Solve 2x + 5 = 15"), "x = 5")

    def test_non_math_returns_none(self):
        self.assertIsNone(evaluate_math("What is a neural network?"))
        self.assertIsNone(evaluate_math("Open Spotify"))
        self.assertIsNone(evaluate_math("Search the web for python"))
        self.assertIsNone(evaluate_math(""))

    def test_division_by_zero(self):
        self.assertIsNone(evaluate_math("100 / 0"))


if __name__ == "__main__":
    unittest.main()
