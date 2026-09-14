import ast
import operator


# Only these operations are allowed.
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate(node: ast.AST) -> float | int:
    """Safely evaluate a mathematical AST."""

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value

        raise ValueError("Only numbers are allowed.")

    if isinstance(node, ast.UnaryOp):
        operation = _OPERATORS.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported unary operator.")

        return operation(_evaluate(node.operand))

    if isinstance(node, ast.BinOp):
        operation = _OPERATORS.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported mathematical operator.")

        left = _evaluate(node.left)
        right = _evaluate(node.right)

        return operation(left, right)

    raise ValueError("Invalid mathematical expression.")


def calculate(expression: str) -> str:
    """
    Safely calculate a mathematical expression.

    Supported:
    +, -, *, /, %, **, parentheses, positive/negative numbers.
    """

    expression = expression.strip()

    if not expression:
        return "No mathematical expression was provided."

    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree.body)

    except ZeroDivisionError:
        return "The calculation failed because division by zero is not allowed."

    except (SyntaxError, ValueError):
        return "I couldn't understand that mathematical expression."

    # Make whole-number floats look nicer.
    if isinstance(result, float) and result.is_integer():
        result = int(result)

    return str(result)