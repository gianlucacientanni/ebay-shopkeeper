# standard library
import ast
import importlib.util as importlib
import io
import logging
import math
import os
import token as t_type
from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path
from tokenize import TokenInfo, tokenize, untokenize
from types import ModuleType
from typing import Dict, List, Optional, TypeVar, Union


T = TypeVar("T")


log = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d - %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class ImportedObject:
    name: str
    ast: ast.AST
    namespaced_name: Optional[str] = None
    alias: Optional[str] = None
    module_from: Optional[ModuleType] = None

    def __eq__(self, __o: object) -> bool:
        return (
            isinstance(__o, type(self))
            and self.name == __o.name
            and self.namespaced_name == __o.namespaced_name
        )

    def __hash__(self) -> int:
        return hash(
            self.name + (self.namespaced_name or "") + getattr(self.module_from, "__name__", "")
        )


@dataclass
class ImportedModule:
    name: str
    module: ModuleType
    alias: Optional[str] = None

    def get_name(self):
        return self.alias or self.name

    def __str__(self) -> str:
        return f"ImportedModule(name={self.name}, alias={self.alias})"

    def __eq__(self, __o: object) -> bool:
        return (
            isinstance(__o, type(self))
            and self.name == __o.name
            and self.alias == __o.alias
            and self.module.__name__ == __o.module.__name__
        )

    def __hash__(self) -> int:
        return hash(self.name + str(self.alias) + self.module.__name__)


class RenderException(Exception):
    pass


def clear_node_location_metadata(node: ast.AST) -> ast.AST:
    """
    When moving a node, the metadata associated with that node needs to be removed.
    ast.fix_missing_locations() is called to repopulate this metadata when required.
    """
    if hasattr(node, "col_offset"):
        node.col_offset = None
    if hasattr(node, "end_col_offset"):
        node.end_col_offset = None
    if hasattr(node, "end_lineno"):
        node.end_lineno = None
    if hasattr(node, "lineno"):
        node.lineno = None
    return node


def combine_module_and_object_name(module_name: str, object_name: str) -> str:
    if len(module_name) > 1:
        if "." in module_name:
            return module_name.split(".")[-1] + "_" + object_name
        else:
            return module_name + "_" + object_name
    else:
        return "_" + object_name


def get_assign_node_target_name(node: ast.Assign) -> Union[str, None]:
    """
    Return the LHS (target) of an Assign node.
    E.g get the my_list node in the statement below
    my_list = [1, 2, 3]

    Tuple assignments are not implemented, so using the syntax below would fail.
    a, b = get_tuple()
    """
    if isinstance(node, ast.Assign):
        if len(node.targets) > 1:
            raise RenderException("Unpacking tuples is not yet implemented.")
        else:
            if isinstance(node.targets[0], ast.Name):
                return node.targets[0].id
            elif isinstance(node.targets[0], ast.Attribute):
                return node.targets[0].attr
            else:
                raise RenderException(f"Unknown target type {type(node.targets[0])}")
    else:
        return None


def get_node_target_name(node: ast.AST) -> Optional[str]:
    """
    Will return the function or object assignment name.
    If the AST node is not of type Assign or FunctionDef, will return None.
    """
    if isinstance(node, ast.Assign):
        return get_assign_node_target_name(node)
    elif isinstance(node, ast.FunctionDef):
        return node.name
    else:
        return None


def compare_ast(node1: Union[ast.AST, List[ast.AST]], node2: Union[ast.AST, List[ast.AST]]) -> bool:
    """
    Do a comparison of two (or more) AST nodes, ignoring metadata.
    """
    if type(node1) is not type(node2):
        return False

    if isinstance(node1, ast.AST):
        for k, v in vars(node1).items():
            if k in ("lineno", "col_offset", "ctx", "end_lineno", "end_col_offset"):
                continue
            if not hasattr(node2, k):
                return False
            if not compare_ast(v, getattr(node2, k)):
                return False
        return True

    elif isinstance(node1, List) and isinstance(node2, List):
        if len(node1) != len(node2):
            return False
        else:
            return all([compare_ast(n1, n2) for n1, n2 in zip(node1, node2)])
    else:
        return node1 == node2


def get_module_filename(module: ModuleType) -> str:
    return os.path.basename(module.__file__)


def remove_quotes_from_module_headers(rendered_contract: str, module_header_identifier: str) -> str:
    """
    The ast module does not preserve comments. This is used as a work-around to allow comments to be
    added to the tree by using an ast.Constant node. The module header prefix is used to determine
    what is and isn't a module header string, so ensure that it is unique enough not to clash with
    other object definitions.
    """

    def strip_header_token(token_value: str) -> str:
        return token_value.replace(module_header_identifier, "").replace('"', "").replace("'", "")

    tokens = tokenize(io.BytesIO(rendered_contract.encode("utf-8")).readline)
    new_tokens: List[TokenInfo] = []
    newlines_added = 0
    header_found = False
    header_whitespace_required = False

    for token in tokens:
        # Check if we need to add a new line below the new module section header
        # We only need to add an NL token if there isn't one directly below
        if header_found:
            # a header has been added, as soon as we find a newline set whitespace required false
            if token.type == t_type.NL:
                if header_whitespace_required:
                    header_whitespace_required = False
                # if we find another new line we need to not add it (continue)
                elif not header_whitespace_required:
                    newlines_added -= 1
                    continue
            # if we have come across a new token type add whitespace if its required
            elif (
                token.type != t_type.NL
                and token.type != t_type.DEDENT
                and module_header_identifier not in token.line
            ):
                header_found = False
                if header_whitespace_required:
                    nl_start = (token.start[0] + newlines_added, token.start[1])
                    nl_end = (token.end[0] + newlines_added, token.end[1])
                    new_tokens.append(
                        TokenInfo(t_type.NL, "\n", (nl_start[0], 0), (nl_end[0], 1), "\n")
                    )
                    newlines_added += 1

        token_start = (token.start[0] + newlines_added, token.start[1])
        token_end = (token.end[0] + newlines_added, token.end[1])

        if module_header_identifier in token.string:
            # check that the previous token is a new line or header line otherwise add an NL 61
            if new_tokens[-1] and (
                module_header_identifier not in new_tokens[-1].line
                and new_tokens[-1].type != t_type.NL
            ):
                nl_start = (token.start[0] + newlines_added, token.start[1])
                nl_end = (token.end[0] + newlines_added, token.end[1])
                new_tokens.append(
                    TokenInfo(t_type.NL, "\n", (nl_start[0], 0), (nl_end[0], 1), "\n")
                )
                newlines_added += 1
                token_start = (token.start[0] + newlines_added, token.start[1])
                token_end = (token.end[0] + newlines_added, token.end[1])

            # Here we need to check whether the previous line is an NL 61
            elif token.type == t_type.STRING and module_header_identifier not in token.line:
                for t in reversed(new_tokens):
                    if t.type == t_type.DEDENT:
                        continue
                    elif t.type != t_type.NL:
                        newlines_added += 2
                        new_tokens.extend(
                            [
                                TokenInfo(
                                    t_type.NL,
                                    "\n",
                                    (token_start[0], 0),
                                    (token_end[0], 1),
                                    "\n",
                                ),
                                TokenInfo(
                                    t_type.NL,
                                    "\n",
                                    (token_start[0] + 1, 0),
                                    (token_end[0] + 1, 1),
                                    "\n",
                                ),
                            ]
                        )
                        token_start = (token.start[0] + newlines_added, token.start[1])
                        token_end = (token.end[0] + newlines_added, token.end[1])
                        break
                    else:
                        break

            new_tokens.append(
                TokenInfo(
                    token.type,
                    strip_header_token(token.string),
                    token_start,
                    token_end,
                    strip_header_token(token.line),
                )
            )
            header_found = True
            header_whitespace_required = True
        else:
            new_tokens.append(
                TokenInfo(token.type, token.string, token_start, token_end, token.line)
            )

    return untokenize(new_tokens).decode("utf-8")


def group_multiline_strings(
    nodes: List[ast.AST],
) -> List[Union[ast.AST, List[ast.AST]]]:
    """
    Group nodes into a lists of nodes where there are multi-line string constants defined.
    The AST module will create multiple independent nodes to represent multi-line strings, making
    it difficult to apply sorting to a list of nodes. In almost all cases, multi-line string nodes
    should be kept grouped together.
    An example of how a multi-line string is represented as an AST is below:

    my_attribute = "Here is an example "
    "of a multi-line string."

    Parsed to an AST (simplified):
    [ast.Assign(), ast.Expr()]
    (The second line of the multi-line string is represented as a Constant node type, separate from
     the Assign node.)

    This will return the original list of nodes, with all multi-line assignments grouped as a list.
    E.g.
    Input: [ast.FunctionDef, ast.FunctionDef, ast.Assign, ast.Expr, ast.Assign, ast.FunctionDef]
    Output: [ast.FunctionDef, ast.FunctionDef, [ast.Assign, ast.Expr], ast.Assign, ast.FunctionDef]
    """
    grouped_multiline_string_nodes: Dict[int, List[ast.AST]] = {}
    assign_const_found = False
    assign_const_found_at = None
    for n, node in enumerate(nodes):
        if assign_const_found:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                if grouped_multiline_string_nodes.get(assign_const_found_at):
                    grouped_multiline_string_nodes[assign_const_found_at].append(node)
                else:
                    grouped_multiline_string_nodes.update(
                        {assign_const_found_at: [nodes[n - 1], node]}
                    )
            else:
                assign_const_found = False
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            assign_const_found = True
            assign_const_found_at = n

    nodes_removed = 0
    for idx, grouped_nodes in sorted(grouped_multiline_string_nodes.items()):
        actual_idx = idx - nodes_removed
        del nodes[actual_idx : actual_idx + len(grouped_nodes)]
        nodes.insert(actual_idx, grouped_nodes)
        nodes_removed += len(grouped_nodes) - 1

    return nodes


def ungroup_nodes(nodes: List[Union[ast.AST, List[ast.AST]]]) -> List[ast.AST]:
    """
    Flatten a list of lists of AST nodes.
    """
    flattened_list = []
    for item in nodes:
        if isinstance(item, list):
            flattened_list.extend(item)
        else:
            flattened_list.append(item)
    return flattened_list


def reorder_nodes(nodes: list[ast.AST], order: list[str]) -> tuple[list[ast.AST], bool]:
    """
    Given a list of AST nodes, reorder them according to the order list.

    :param order: Order list defines the order in which to arrange the definition nodes, e.g.
    [
        "display_name",
        "description",
        "pre_posting_code",
        "post_posting_code"
    ]
    In this example, the return list will contain each of the definitions in the same order.
    Objects that do not match any entries in the order list are moved below all those that do
    match. Meaning that any objects defined in the order list are guaranteed to be at the top of
    the returned list (the top being index 0).
    :return tuple: list of ordered nodes, bool to state whether the order has changed
    """
    grouped_nodes = group_multiline_strings(nodes)
    order_val = dict((name, i) for i, name in enumerate(order))
    order_changed = False

    def sort_metadata(node1: ast.AST, node2: ast.AST):
        nonlocal order_changed

        if isinstance(node1, list):
            node1 = node1[0]
        if isinstance(node2, list):
            node2 = node2[0]

        node1_name = get_node_target_name(node1)
        node2_name = get_node_target_name(node2)

        # math.inf is used as the default to ensure that undefined order items always fall below
        # those defined in the order list
        node1_order_value = order_val.get(node1_name, math.inf)
        node2_order_value = order_val.get(node2_name, math.inf)

        if not order_changed:
            order_changed = node1_order_value != math.inf or node2_order_value != math.inf

        if node1_order_value == node2_order_value:
            return 0
        elif node1_order_value < node2_order_value:
            return -1
        else:
            return 1

    grouped_nodes = sorted(grouped_nodes, key=cmp_to_key(sort_metadata))
    return ungroup_nodes(grouped_nodes), order_changed


def remove_remaining_headers(nodes: list[ast.AST], header_prefix: str) -> list[ast.AST]:
    """
    Removes any stray unused headers that may be left at the bottom of the list.
    This could happen if all objects from the template have been moved to the top of the file.
    """
    while (
        isinstance(nodes[-1], ast.Expr)
        and isinstance(nodes[-1].value, ast.Constant)
        and header_prefix in nodes[-1].value.value
    ):
        nodes.pop(-1)
    return nodes


def module_header_nodes(headers: List[str]) -> List[ast.AST]:
    return [ast.Expr(value=ast.Constant(value=header)) for header in headers]


def load_module_from_filepath(module_filepath: str) -> ModuleType:
    spec = importlib.spec_from_file_location(Path(module_filepath).stem, module_filepath)
    if spec and spec.loader:
        template_module = importlib.module_from_spec(spec)
        spec.loader.exec_module(template_module)
        return template_module
    else:
        raise ImportError(f"Unable to load module from {module_filepath}, invalid spec")


def recursive_topological_sort(graph: dict[T, list[T]], node: T) -> list[T]:
    """
    Implementation of a recursive DFS algorithm storing result for topological order.
    """
    result = []
    seen = set()

    def recursive_helper(node):
        for neighbour in graph.get(node, []):
            if neighbour not in seen:
                seen.add(neighbour)
                recursive_helper(neighbour)
        result.append(node)

    recursive_helper(node)
    return result


class ObjectReferenceFound(Exception):
    pass


class ObjectReferenceDiscovery(ast.NodeVisitor):
    def __init__(self, reference_to_find: str) -> None:
        self.reference_to_find = reference_to_find
        super().__init__()

    def visit_Name(self, node: ast.Name):
        if node.id == self.reference_to_find:
            # When the first object reference is found we can return to the caller
            # by raising an exception to immediately halt traversal of the AST
            raise ObjectReferenceFound()
        return self.generic_visit(node)


def is_object_referenced(obj: ImportedObject, ast_to_search: ast.AST) -> bool:
    try:
        if not obj.namespaced_name:
            raise ValueError("namespaced_name not set")
        ObjectReferenceDiscovery(obj.namespaced_name).visit(ast_to_search)
        return False
    except ObjectReferenceFound:
        return True


def get_unreferenced_objects(
    object_reference_map: dict[ImportedObject, list[Union[ImportedObject, str]]]
) -> list[ImportedObject]:
    """
    Taking each object in object_reference_map, check against the map to see if it is referenced,
    either directly or indirectly. Below is a pseudo example of an object_reference_map:
    {
        get_postings: [create_postings],
        str_to_bool: [get_postings, is_active, get_parameter]
        get_parameter: []
        is_active: [retrieve_product]
        create_postings: []
    }
    In the example data, we should remove get_postings, get_parameter and create_postings as they
    are either not referenced directly or indirectly (get_postings is referenced by create_postings
    but create_postings isn't referenced at all - so both should be removed).

    :param object_reference_map: mapping of object to objects that reference it
    """

    objects_not_referenced = []

    def obj_not_referenced(obj: Union[ImportedObject, str]) -> bool:
        """
        Helper function to determine if obj is referenced.
        """
        if isinstance(obj, str):
            # obj reference comes from the template so can be ignored
            return False
        elif not object_reference_map[obj]:
            # current obj is not referenced
            return True
        else:
            return all(obj_not_referenced(o) for o in object_reference_map[obj])

    for object_to_import, references in object_reference_map.items():
        if all(obj_not_referenced(obj) for obj in references):
            objects_not_referenced.append(object_to_import)

    return objects_not_referenced