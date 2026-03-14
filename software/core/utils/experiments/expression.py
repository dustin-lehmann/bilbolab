import ast
import re
from typing import Any

from core.utils.logging_utils import Logger

logger = Logger('ExpressionEngine')

# Regex patterns for expression syntax
_EXPR_PATTERN = re.compile(r'\$\{(.+?)\}')  # ${expr}
_REF_PATTERN = re.compile(r'\$([a-zA-Z_][a-zA-Z0-9_.:]*)')  # $var, $action.output, $action:param
_FULL_EXPR_PATTERN = re.compile(r'^\$\{(.+)\}$')  # entire string is ${expr}
_FULL_REF_PATTERN = re.compile(r'^\$([a-zA-Z_][a-zA-Z0-9_.:]+)$')  # entire string is $ref (with dot/colon)
_SIMPLE_REF_PATTERN = re.compile(r'^\$([a-zA-Z_][a-zA-Z0-9_]*)$')  # entire string is $simple_var

# Whitelisted safe functions
_SAFE_FUNCTIONS = {
    'min': min,
    'max': max,
    'abs': abs,
    'round': round,
    'len': len,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'list': list,
    'range': range,
    'sum': sum,
    'tuple': tuple,
    # YAML/JSON-style boolean and null literals
    'true': True,
    'false': False,
    'null': None,
}

# Whitelisted AST node types
_ALLOWED_NODES = {
    ast.Expression,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Subscript,
    ast.Index,  # Python 3.8 compat (no-op in 3.9+)
    ast.Slice,
    ast.Attribute,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.Starred,
    # Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
}


class ExpressionError(Exception):
    pass


class ExpressionEngine:
    """Safe expression evaluator using Python's ast module.

    Supports:
        - $var or ${var}: simple variable reference
        - ${expr}: arithmetic/comparison expressions
        - $action_id.output_name: action output reference
        - $action_id:param_name: action parameter reference
    """

    def __init__(self):
        self._safe_functions = dict(_SAFE_FUNCTIONS)

    def is_expression(self, value: Any) -> bool:
        """Check if a value contains expression syntax."""
        if not isinstance(value, str):
            return False
        return bool(_EXPR_PATTERN.search(value) or _REF_PATTERN.search(value))

    def evaluate(self, expr_str: str, scope: dict[str, Any]) -> Any:
        """Evaluate an expression string against a scope dict.

        Args:
            expr_str: Expression like "${counter + 1}" or "$var"
            scope: Variable mapping for name resolution

        Returns:
            Evaluated result

        Raises:
            ExpressionError: If expression is invalid or uses disallowed operations
        """
        preprocessed = self._preprocess(expr_str)
        transformed_scope = self._transform_scope(scope)

        try:
            tree = ast.parse(preprocessed, mode='eval')
        except SyntaxError as e:
            raise ExpressionError(f"Syntax error in expression '{expr_str}': {e}") from e

        self._validate_ast(tree, expr_str)

        code = compile(tree, f'<expr: {expr_str}>', 'eval')
        # User scope takes precedence over safe functions (e.g. variable 'sum' over builtin sum)
        eval_scope = {**self._safe_functions, **transformed_scope}

        try:
            return eval(code, {'__builtins__': {}}, eval_scope)
        except Exception as e:
            raise ExpressionError(f"Error evaluating '{expr_str}': {e}") from e

    def resolve_value(self, value: Any, scope: dict[str, Any]) -> Any:
        """Resolve expressions in a value, recursively handling dicts and lists.

        - If value is a string that is entirely an expression, returns the typed result
        - If value is a string with embedded expressions, returns a string
        - Dicts and lists are resolved recursively
        - Non-string, non-container values pass through unchanged
        """
        if isinstance(value, str):
            return self._resolve_string(value, scope)
        elif isinstance(value, dict):
            return {k: self.resolve_value(v, scope) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_value(v, scope) for v in value]
        return value

    def _resolve_string(self, value: str, scope: dict[str, Any]) -> Any:
        """Resolve a single string value."""
        # Full expression: ${expr} — preserve type
        match = _FULL_EXPR_PATTERN.match(value)
        if match:
            return self.evaluate(match.group(1), scope)

        # Full reference with dot/colon: $action.output or $action:param — preserve type
        match = _FULL_REF_PATTERN.match(value)
        if match:
            return self.evaluate(match.group(1), scope)

        # Simple variable reference: $var — preserve type
        match = _SIMPLE_REF_PATTERN.match(value)
        if match:
            key = match.group(1)
            if key in scope:
                return scope[key]
            return self.evaluate(key, scope)

        # Mixed string with embedded expressions: "text ${expr} more text"
        if _EXPR_PATTERN.search(value) or _REF_PATTERN.search(value):
            result = value
            # Replace ${expr} patterns
            result = _EXPR_PATTERN.sub(
                lambda m: str(self.evaluate(m.group(1), scope)), result
            )
            # Replace $ref patterns (but not inside already-resolved ${})
            result = _REF_PATTERN.sub(
                lambda m: str(self._resolve_ref(m.group(1), scope)), result
            )
            return result

        return value

    def _resolve_ref(self, ref: str, scope: dict[str, Any]) -> Any:
        """Resolve a bare reference like 'action.output' or 'action:param'."""
        # Direct scope lookup first
        if ref in scope:
            return scope[ref]

        # Try as expression
        try:
            return self.evaluate(ref, scope)
        except ExpressionError:
            raise ExpressionError(f"Unresolved reference: ${ref}")

    def _preprocess(self, expr_str: str) -> str:
        """Transform expression syntax into valid Python for ast.parse.

        - $action_id.output -> __ao_action_id__output
        - $action_id:param  -> __ap_action_id__param
        - $var              -> var
        - ${expr}           -> expr (delimiters stripped)
        """
        s = expr_str.strip()

        # Strip ${...} delimiters
        match = _FULL_EXPR_PATTERN.match(s)
        if match:
            s = match.group(1)

        # Strip leading $ for simple refs
        if s.startswith('$'):
            s = s[1:]

        # Replace action:param references -> __ap_action__param
        s = re.sub(
            r'([a-zA-Z_][a-zA-Z0-9_]*):([a-zA-Z_][a-zA-Z0-9_]*)',
            r'__ap_\1__\2',
            s
        )

        # Replace action.output references -> __ao_action__output
        # Only replace dotted refs that look like identifiers (not method calls or attribute chains)
        s = re.sub(
            r'([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)(?![.\(])',
            r'__ao_\1__\2',
            s
        )

        return s

    def _transform_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        """Transform scope keys to match preprocessed variable names."""
        transformed = {}
        for key, value in scope.items():
            transformed[key] = value
            # action_id.output -> __ao_action_id__output
            if '.' in key:
                parts = key.split('.', 1)
                transformed[f'__ao_{parts[0]}__{parts[1]}'] = value
            # action_id:param -> __ap_action_id__param
            if ':' in key:
                parts = key.split(':', 1)
                transformed[f'__ap_{parts[0]}__{parts[1]}'] = value
        return transformed

    def _validate_ast(self, tree: ast.AST, original_expr: str):
        """Walk AST and reject disallowed node types."""
        for node in ast.walk(tree):
            if type(node) not in _ALLOWED_NODES:
                raise ExpressionError(
                    f"Disallowed operation '{type(node).__name__}' in expression '{original_expr}'"
                )
            # Validate function calls are whitelisted
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id not in self._safe_functions:
                        raise ExpressionError(
                            f"Function '{node.func.id}' is not allowed in expression '{original_expr}'"
                        )
                elif not isinstance(node.func, ast.Attribute):
                    raise ExpressionError(
                        f"Complex function calls not allowed in expression '{original_expr}'"
                    )
