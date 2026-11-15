# standard library
import ast
import unittest
from unittest import TestCase

# inception imports
from inception_sdk.vault.contracts.types_extension import _ALL_TYPES  # type: ignore[import-not-found]
from inception_sdk.tools.renderer.render_utils import (  # type: ignore[import-not-found]
    clear_node_location_metadata,
    combine_module_and_object_name,
    compare_ast,
    get_assign_node_target_name,
    get_node_target_name,
    group_multiline_strings,
    remove_remaining_headers,
    reorder_nodes,
    ungroup_nodes,
)
from inception_sdk.tools.renderer.renderer import RendererConfig  # type: ignore[import-not-found]


VAULT_TYPES = list(_ALL_TYPES.keys()) + ["vault"]
API_ASSIGN_NODE = ast.Assign(
    targets=[ast.Name(id="api", ctx=ast.Store())],
    value=ast.Constant(value="3.9.0", kind=None),
    lineno=1,
)
VERSION_ASSIGN_NODE = ast.Assign(
    targets=[ast.Name(id="version", ctx=ast.Store())],
    value=ast.Constant(value="1.0.0", kind=None),
    lineno=2,
)


class RenderUtilsTest(TestCase):
    def test_clear_node_location_metadata(self):
        node = ast.Name(
            id="name",
            col_offset=1,
            end_col_offset=2,
            lineno=3,
            end_lineno=4,
        )
        node = clear_node_location_metadata(node)
        self.assertEqual(node.col_offset, None)
        self.assertEqual(node.end_col_offset, None)
        self.assertEqual(node.lineno, None)
        self.assertEqual(node.end_lineno, None)

    def test_combine_module_and_object_name(self):
        new_object_name = combine_module_and_object_name("tools.renderer.render_utils", "test")
        self.assertEqual(new_object_name, "render_utils_test")

    def test_combine_module_and_object_name_no_dots_in_name(self):
        new_object_name = combine_module_and_object_name("render_utils", "test")
        self.assertEqual(new_object_name, "render_utils_test")

    def test_combine_module_and_object_name_just_dot(self):
        # this scenario occurs if a module does a relative import
        # e.g. from . import my_module
        new_object_name = combine_module_and_object_name(".", "test")
        self.assertEqual(new_object_name, "_test")

    def test_get_assign_node_target_name(self):
        assign_node = ast.Assign(
            targets=[ast.Name(ctx=ast.Store(), id="days_in_year")], value=ast.Constant(value=365)
        )
        target_name = get_assign_node_target_name(assign_node)
        self.assertEqual(target_name, "days_in_year")

    def test_get_assign_node_target_name_not_assign_node(self):
        assign_node = ast.Constant(value=365)
        target_name = get_assign_node_target_name(assign_node)
        self.assertFalse(target_name)

    def test_compare_ast_true(self):
        test_cases = [
            {
                "description": "simple single level comparison",
                "ast_object_1": ast.Name(id="name"),
                "ast_object_2": ast.Name(id="name"),
            },
            {
                "description": "simple single level comparison with ignored attributes",
                "ast_object_1": ast.Name(id="name", lineno=1),
                "ast_object_2": ast.Name(id="name", lineno=2),
            },
            {
                "description": "simple multiple level comparison",
                "ast_object_1": ast.Attribute(value=ast.Name(id="1")),
                "ast_object_2": ast.Attribute(value=ast.Name(id="1")),
            },
            {
                "description": "complex multiple level comparison with ignored attributes",
                "ast_object_1": ast.Module(
                    body=[
                        API_ASSIGN_NODE,
                        VERSION_ASSIGN_NODE,
                    ]
                ),
                "ast_object_2": ast.Module(
                    body=[
                        ast.Assign(
                            targets=[
                                ast.Name(
                                    lineno=1,
                                    col_offset=0,
                                    end_lineno=14,
                                    end_col_offset=3,
                                    id="api",
                                    ctx=ast.Store(),
                                )
                            ],
                            value=ast.Constant(
                                lineno=1,
                                col_offset=6,
                                end_lineno=14,
                                end_col_offset=13,
                                value="3.9.0",
                                kind=None,
                            ),
                        ),
                        ast.Assign(
                            targets=[
                                ast.Name(
                                    lineno=28,
                                    col_offset=0,
                                    end_lineno=15,
                                    end_col_offset=7,
                                    id="version",
                                    ctx=ast.Store(),
                                )
                            ],
                            value=ast.Constant(
                                lineno=28,
                                col_offset=10,
                                end_lineno=15,
                                end_col_offset=17,
                                value="1.0.0",
                                kind=None,
                            ),
                        ),
                    ]
                ),
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertTrue(
                compare_ast(test_case["ast_object_1"], test_case["ast_object_2"]),
                f"Test case {test_desc} failed.",
            )

    def test_compare_ast_false(self):
        test_cases = [
            {
                "description": "Same Class different attributes",
                "ast_object_1": ast.Name(id="1"),
                "ast_object_2": ast.Name(id="2"),
            },
            {
                "description": "Different Class same attributes",
                "ast_object_1": ast.Name(id="1"),
                "ast_object_2": ast.Attribute(id="1"),
            },
            {
                "description": "Different attributes on value object",
                "ast_object_1": ast.Attribute(value=ast.Name(id="1")),
                "ast_object_2": ast.Attribute(value=ast.Name(id="2")),
            },
            {
                "description": "Multiple levels of attributes",
                "ast_object_1": ast.Module(
                    body=[
                        API_ASSIGN_NODE,
                        VERSION_ASSIGN_NODE,
                    ]
                ),
                "ast_object_2": ast.Module(
                    body=[
                        API_ASSIGN_NODE,
                        ast.Assign(
                            targets=[ast.Name(id="version", ctx=ast.Store())],
                            value=ast.Constant(value="1.1.0", kind=None),
                        ),
                    ]
                ),
            },
        ]

        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertFalse(
                compare_ast(test_case["ast_object_1"], test_case["ast_object_2"]),
                f"Test case {test_desc} failed.",
            )

    def test_group_multiline_strings(self):
        self.maxDiff = None
        nodes = [
            API_ASSIGN_NODE,
            VERSION_ASSIGN_NODE,
            ast.Assign(
                targets=[ast.Name(id="summary", ctx=ast.Store())],
                value=ast.Constant(value="This is a ", kind=None),
                lineno=3,
            ),
            ast.Expr(value=ast.Constant(value="test product."), lineno=4),
            ast.Assign(
                targets=[ast.Name(id="supported_denomination", ctx=ast.Store())],
                value=ast.Constant(value="GBP", kind=None),
                lineno=5,
            ),
            ast.Assign(
                targets=[ast.Name(id="description", ctx=ast.Store())],
                value=ast.Constant(value="More unit tests ", kind=None),
                lineno=6,
            ),
            ast.Expr(value=ast.Constant(value="please."), lineno=7),
        ]
        expected_output = [
            API_ASSIGN_NODE,
            VERSION_ASSIGN_NODE,
            [
                ast.Assign(
                    targets=[ast.Name(id="summary", ctx=ast.Store())],
                    value=ast.Constant(value="This is a ", kind=None),
                    lineno=3,
                ),
                ast.Expr(value=ast.Constant(value="test product."), lineno=4),
            ],
            ast.Assign(
                targets=[ast.Name(id="supported_denomination", ctx=ast.Store())],
                value=ast.Constant(value="GBP", kind=None),
                lineno=5,
            ),
            [
                ast.Assign(
                    targets=[ast.Name(id="description", ctx=ast.Store())],
                    value=ast.Constant(value="More unit tests ", kind=None),
                    lineno=6,
                ),
                ast.Expr(value=ast.Constant(value="please."), lineno=7),
            ],
        ]
        nodes = group_multiline_strings(nodes)
        self.assertEqual(ast.unparse(nodes), ast.unparse(expected_output))

    def test_ungroup_nodes(self):
        self.maxDiff = None
        nodes = [
            API_ASSIGN_NODE,
            VERSION_ASSIGN_NODE,
            [
                ast.Assign(
                    targets=[ast.Name(id="summary", ctx=ast.Store())],
                    value=ast.Constant(value="This is a ", kind=None),
                    lineno=3,
                ),
                ast.Expr(value=ast.Constant(value="test product."), lineno=4),
            ],
            ast.Assign(
                targets=[ast.Name(id="supported_denomination", ctx=ast.Store())],
                value=ast.Constant(value="GBP", kind=None),
                lineno=5,
            ),
            [
                ast.Assign(
                    targets=[ast.Name(id="description", ctx=ast.Store())],
                    value=ast.Constant(value="More unit tests ", kind=None),
                    lineno=6,
                ),
                ast.Expr(value=ast.Constant(value="please."), lineno=7),
            ],
        ]
        expected_output = [
            API_ASSIGN_NODE,
            VERSION_ASSIGN_NODE,
            ast.Assign(
                targets=[ast.Name(id="summary", ctx=ast.Store())],
                value=ast.Constant(value="This is a ", kind=None),
                lineno=3,
            ),
            ast.Expr(value=ast.Constant(value="test product."), lineno=4),
            ast.Assign(
                targets=[ast.Name(id="supported_denomination", ctx=ast.Store())],
                value=ast.Constant(value="GBP", kind=None),
                lineno=5,
            ),
            ast.Assign(
                targets=[ast.Name(id="description", ctx=ast.Store())],
                value=ast.Constant(value="More unit tests ", kind=None),
                lineno=6,
            ),
            ast.Expr(value=ast.Constant(value="please."), lineno=7),
        ]
        nodes = ungroup_nodes(nodes)
        self.assertEqual(ast.unparse(nodes), ast.unparse(expected_output))

    def test_reorder_nodes(self):
        nodes = [
            VERSION_ASSIGN_NODE,
            ast.Assign(
                targets=[ast.Name(id="summary", ctx=ast.Store())],
                value=ast.Constant(value="This is a ", kind=None),
                lineno=2,
            ),
            ast.Expr(value=ast.Constant(value="test product."), lineno=3),
            ast.Assign(
                targets=[ast.Name(id="display_name", ctx=ast.Store())],
                value=ast.Constant(value="Test Product", kind=None),
                lineno=4,
            ),
            API_ASSIGN_NODE,
            ast.Assign(
                targets=[ast.Name(id="description", ctx=ast.Store())],
                value=ast.Constant(value="More unit tests ", kind=None),
                lineno=6,
            ),
            ast.Expr(value=ast.Constant(value="please."), lineno=7),
        ]

        expected_output = [
            API_ASSIGN_NODE,
            VERSION_ASSIGN_NODE,
            ast.Assign(
                targets=[ast.Name(id="display_name", ctx=ast.Store())],
                value=ast.Constant(value="Test Product", kind=None),
                lineno=3,
            ),
            ast.Assign(
                targets=[ast.Name(id="description", ctx=ast.Store())],
                value=ast.Constant(value="More unit tests ", kind=None),
                lineno=4,
            ),
            ast.Expr(value=ast.Constant(value="please."), lineno=5),
            ast.Assign(
                targets=[ast.Name(id="summary", ctx=ast.Store())],
                value=ast.Constant(value="This is a ", kind=None),
                lineno=6,
            ),
            ast.Expr(value=ast.Constant(value="test product."), lineno=7),
        ]

        order = [
            "api",
            "version",
            "display_name",
            "description",
            "summary",
        ]

        nodes, order_changed = reorder_nodes(nodes, order)
        self.assertEqual(ast.unparse(nodes), ast.unparse(expected_output))
        self.assertTrue(order_changed)

    def test_reorder_nodes_incl_func_defs_and_missing_objects(self):
        nodes = [
            ast.FunctionDef(
                name="pre_posting_code",
                args=[],
                body=[
                    ast.Assign(
                        targets=[ast.Name(id="denomination", ctx=ast.Store())],
                        value=ast.Constant(value="GBP", kind=None),
                        lineno=3,
                    )
                ],
                decorator_list=[],
                lineno=2,
            ),
            ast.Assign(
                targets=[ast.Name(id="summary", ctx=ast.Store())],
                value=ast.Constant(value="This is a ", kind=None),
                lineno=4,
            ),
            ast.Expr(value=ast.Constant(value="test product."), lineno=3),
            ast.Assign(
                targets=[ast.Name(id="api", ctx=ast.Store())],
                value=ast.Constant(value="3.9.0", kind=None),
                lineno=7,
            ),
            ast.Assign(
                targets=[ast.Name(id="description", ctx=ast.Store())],
                value=ast.Constant(value="More unit tests ", kind=None),
                lineno=8,
            ),
            ast.Expr(value=ast.Constant(value="please."), lineno=7),
        ]

        expected_output = [
            ast.Assign(
                targets=[ast.Name(id="api", ctx=ast.Store())],
                value=ast.Constant(value="3.9.0", kind=None),
                lineno=1,
            ),
            ast.Assign(
                targets=[ast.Name(id="description", ctx=ast.Store())],
                value=ast.Constant(value="More unit tests ", kind=None),
                lineno=4,
            ),
            ast.Expr(value=ast.Constant(value="please."), lineno=5),
            ast.Assign(
                targets=[ast.Name(id="summary", ctx=ast.Store())],
                value=ast.Constant(value="This is a ", kind=None),
                lineno=6,
            ),
            ast.Expr(value=ast.Constant(value="test product."), lineno=7),
            ast.FunctionDef(
                name="pre_posting_code",
                args=[],
                body=[
                    ast.Assign(
                        targets=[ast.Name(id="denomination", ctx=ast.Store())],
                        value=ast.Constant(value="GBP", kind=None),
                        lineno=9,
                    )
                ],
                decorator_list=[],
                lineno=8,
            ),
        ]

        order = [
            "api",
            "version",
            "display_name",
            "description",
            "summary",
            "pre_posting_code",
        ]

        nodes, order_changed = reorder_nodes(nodes, order)
        self.assertEqual(ast.unparse(nodes), ast.unparse(expected_output))
        self.assertTrue(order_changed)

    def test_get_node_target_name_assign(self):
        func_def_node = ast.FunctionDef(
            name="pre_posting_code",
            args=[],
            body=[
                ast.Assign(
                    targets=[ast.Name(id="denomination", ctx=ast.Store())],
                    value=ast.Constant(value="GBP", kind=None),
                    lineno=2,
                )
            ],
            decorator_list=[],
            lineno=1,
        )
        name = get_node_target_name(func_def_node)
        self.assertEqual(name, "pre_posting_code")

    def test_get_node_target_name_function_def(self):
        assign_node = ast.Assign(
            targets=[ast.Name(id="api", ctx=ast.Store())],
            value=ast.Constant(value="3.9.0", kind=None),
            lineno=1,
        )
        name = get_node_target_name(assign_node)
        self.assertEqual(name, "api")

    def test_get_node_target_name_unknown_type(self):
        unknown_node = "test"
        name = get_node_target_name(unknown_node)
        self.assertEqual(name, None)

    def test_remove_remaining_headers(self):
        header_prefix = RendererConfig().module_header_prefix
        nodes = [
            ast.Assign(
                targets=[ast.Name(id="api", ctx=ast.Store())],
                value=ast.Constant(value="3.9.0", kind=None),
                lineno=1,
            ),
            ast.Expr(value=ast.Constant(value=header_prefix + "module.py")),
        ]

        nodes = remove_remaining_headers(nodes, header_prefix)

        expected_output = [
            ast.Assign(
                targets=[ast.Name(id="api", ctx=ast.Store())],
                value=ast.Constant(value="3.9.0", kind=None),
                lineno=1,
            )
        ]
        self.assertEqual(ast.unparse(nodes), ast.unparse(expected_output))

    def test_remove_remaining_headers_multiple(self):
        header_prefix = RendererConfig().module_header_prefix
        nodes = [
            ast.Expr(value=ast.Constant(value=header_prefix + "module.py")),
            ast.Assign(
                targets=[ast.Name(id="api", ctx=ast.Store())],
                value=ast.Constant(value="3.9.0", kind=None),
                lineno=1,
            ),
            ast.Expr(value=ast.Constant(value=header_prefix + "module1.py")),
            ast.Expr(value=ast.Constant(value=header_prefix + "module2.py")),
        ]

        nodes = remove_remaining_headers(nodes, header_prefix)

        expected_output = [
            ast.Expr(value=ast.Constant(value=header_prefix + "module.py")),
            ast.Assign(
                targets=[ast.Name(id="api", ctx=ast.Store())],
                value=ast.Constant(value="3.9.0", kind=None),
                lineno=1,
            ),
        ]
        self.assertEqual(ast.unparse(nodes), ast.unparse(expected_output))


if __name__ == "__main__":
    unittest.main()