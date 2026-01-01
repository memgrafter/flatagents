"""
CEL expression engine for flatmachines.

Wraps cel-python to provide full CEL support including:
- List macros (all, exists, filter, map)
- String methods (startsWith, contains, endsWith)
- Timestamps and durations
- Type coercion

Requires: pip install flatagents[cel]
"""

from typing import Any, Dict

try:
    import celpy
    from celpy import celtypes
    CEL_AVAILABLE = True
except ImportError:
    CEL_AVAILABLE = False


class CELExpressionEngine:
    """
    CEL expression engine using cel-python.
    
    Provides full CEL support for advanced expressions.
    """

    def __init__(self):
        if not CEL_AVAILABLE:
            raise ImportError(
                "CEL expression engine requires cel-python. "
                "Install with: pip install flatagents[cel]"
            )
        self._env = celpy.Environment()

    def evaluate(self, expression: str, variables: Dict[str, Any]) -> Any:
        """
        Evaluate a CEL expression with the given variables.

        Args:
            expression: The CEL expression string to evaluate
            variables: Dictionary of variable names to values

        Returns:
            The result of evaluating the expression

        Raises:
            ValueError: If expression syntax is invalid
        """
        if not expression or not expression.strip():
            return True  # Empty expression is always true

        try:
            # Parse the expression
            ast = self._env.compile(expression)
            
            # Create the program
            prog = self._env.program(ast)
            
            # Convert Python values to CEL types
            cel_vars = self._to_cel_types(variables)
            
            # Evaluate
            result = prog.evaluate(cel_vars)
            
            # Convert result back to Python
            return self._from_cel_type(result)
            
        except Exception as e:
            raise ValueError(f"CEL expression error: {expression} - {e}") from e

    def _to_cel_types(self, obj: Any) -> Any:
        """Convert Python types to CEL types."""
        if isinstance(obj, dict):
            return {k: self._to_cel_types(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._to_cel_types(v) for v in obj]
        # Primitives pass through
        return obj

    def _from_cel_type(self, obj: Any) -> Any:
        """Convert CEL types back to Python types."""
        if CEL_AVAILABLE:
            if isinstance(obj, celtypes.BoolType):
                return bool(obj)
            if isinstance(obj, celtypes.IntType):
                return int(obj)
            if isinstance(obj, celtypes.DoubleType):
                return float(obj)
            if isinstance(obj, celtypes.StringType):
                return str(obj)
            if isinstance(obj, celtypes.ListType):
                return [self._from_cel_type(v) for v in obj]
            if isinstance(obj, celtypes.MapType):
                return {k: self._from_cel_type(v) for k, v in obj.items()}
        return obj


__all__ = ["CELExpressionEngine", "CEL_AVAILABLE"]
