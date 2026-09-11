"""Safety checks for test generators whose cost can grow with repository data."""

from __future__ import annotations

import ast
import pathlib
import unittest


TESTS = pathlib.Path(__file__).resolve().parent
COMBINATORIAL_CALLS = {
    "combinations",
    "combinations_with_replacement",
    "permutations",
    "product",
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


class TestGeneratorSafetyTest(unittest.TestCase):
    def test_dynamic_combinatorial_iterators_are_not_nested_in_generators(self):
        """A data-sized product inside another generator can make test cost exponential."""
        offenders = []
        generator_nodes = (ast.For, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

        for path in sorted(TESTS.glob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            parents: dict[ast.AST, ast.AST] = {}
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    parents[child] = parent

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or _call_name(node) not in COMBINATORIAL_CALLS:
                    continue
                if path.name == "combinatorics.py":
                    continue
                parent = parents.get(node)
                while parent is not None and not isinstance(
                    parent, (ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    if isinstance(parent, generator_nodes):
                        offenders.append(f"{path.name}:{node.lineno}")
                        break
                    parent = parents.get(parent)

        self.assertEqual(
            offenders,
            [],
            "dynamic combinatorial iterator nested in a generator; replace exhaustive enumeration "
            "with bounded contract witnesses",
        )


if __name__ == "__main__":
    unittest.main()
