"""
Expression engines for flatmachines.

Provides two modes:
- simple: Built-in parser for basic comparisons and boolean logic (default)
- cel: Full CEL support via cel-python (optional extra)
"""

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class ExpressionEngine(Protocol):
    """Protocol for expression engines."""

    def evaluate(self, expression: str, variables: Dict[str, Any]) -> Any:
        """
        Evaluate an expression with the given variables.

        Args:
            expression: The expression string to evaluate
            variables: Dictionary of variable names to values
                      (e.g., {"context": {...}, "input": {...}, "output": {...}})

        Returns:
            The result of evaluating the expression
        """
        ...


def get_expression_engine(mode: str = "simple") -> ExpressionEngine:
    """
    Get an expression engine by mode.

    Args:
        mode: "simple" (default) or "cel"

    Returns:
        ExpressionEngine instance

    Raises:
        ImportError: If CEL mode requested but cel-python not installed
        ValueError: If unknown mode
    """
    if mode == "simple":
        from .simple import SimpleExpressionEngine
        return SimpleExpressionEngine()
    elif mode == "cel":
        try:
            from .cel import CELExpressionEngine
            return CELExpressionEngine()
        except ImportError:
            raise ImportError(
                "CEL expression engine requires: pip install flatagents[cel]"
            )
    else:
        raise ValueError(f"Unknown expression engine: {mode}")


__all__ = ["ExpressionEngine", "get_expression_engine"]
