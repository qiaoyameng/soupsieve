"""
Versioned JSON serialization for compiled selector graphs.

A compiled :class:`~soupsieve.css_match.SoupSieve` is shared between Python workers as plain
JSON rather than pickle. The document stores the actual compiled selector graph: every node
is flattened into a table of fixed node types and fixed fields, shared sub-structures are
preserved through index references, and the regex patterns used for matching are stored as
compiled pattern data instead of being rebuilt from the original CSS text.

Loading never imports an arbitrary Python class and never reparses the original CSS. A node
table is only accepted when every reference, field and node type validates, and every child
index points at an earlier node, which rules out cycles before any object is constructed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, cast

from . import css_match as cm
from . import css_parser as cp
from . import css_types as ct
from . import util

__all__ = ('GRAPH_VERSION', 'GraphFormatError', 'graph_to_json', 'graph_from_json')

#: Only documents carrying this version are accepted; any other value is rejected.
GRAPH_VERSION = 1

#: Maximum number of nodes accepted in a single graph document.
GRAPH_NODE_LIMIT = 100_000


class GraphFormatError(ValueError):
    """Raised when a JSON selector graph document is malformed or unsupported."""


@dataclass(frozen=True)
class _Field:
    """Description of one fixed field of a node type."""

    kind: str
    targets: tuple[type[ct.Immutable], ...] = ()
    nullable_items: bool = False


@dataclass(frozen=True)
class _Spec:
    """Description of one fixed node type."""

    cls: type[ct.Immutable]
    fields: tuple[_Field, ...]


def _spec(cls: type[ct.Immutable], *fields: _Field) -> _Spec:
    """Build a node specification from the node class and its fixed fields."""

    return _Spec(cls, fields)


# Leaf field encoders, keyed by field kind.
_ENCODERS: dict[str, Callable[[Any], Any]] = {
    'str': lambda value: value,
    'str_or_none': lambda value: value,
    'bool': lambda value: value,
    'int': lambda value: value,
    'str_tuple': lambda value: list(value),
    'pattern': lambda value: None if value is None else value.pattern,
}

# The node types and fields that a version 1 document may contain. Nothing else is allowed.
_SPECS: dict[str, _Spec] = {
    'SelectorTag': _spec(
        ct.SelectorTag,
        _Field('str'),
        _Field('str_or_none'),
    ),
    'SelectorAttribute': _spec(
        ct.SelectorAttribute,
        _Field('str'),
        _Field('str'),
        _Field('pattern'),
        _Field('pattern'),
        _Field('bool'),
        _Field('bool'),
    ),
    'SelectorContains': _spec(
        ct.SelectorContains,
        _Field('str_tuple'),
        _Field('bool'),
    ),
    'SelectorNth': _spec(
        ct.SelectorNth,
        _Field('int'),
        _Field('bool'),
        _Field('int'),
        _Field('bool'),
        _Field('bool'),
        _Field('ref', (ct.SelectorList,)),
    ),
    'SelectorLang': _spec(
        ct.SelectorLang,
        _Field('str_tuple'),
    ),
    'SelectorList': _spec(
        ct.SelectorList,
        _Field('ref_tuple', (ct.Selector,), nullable_items=True),
        _Field('bool'),
        _Field('bool'),
        _Field('int'),
    ),
    'Selector': _spec(
        ct.Selector,
        _Field('ref_or_none', (ct.SelectorTag,)),
        _Field('str_tuple'),
        _Field('str_tuple'),
        _Field('ref_tuple', (ct.SelectorAttribute,)),
        _Field('ref_tuple', (ct.SelectorNth,)),
        _Field('ref_tuple', (ct.SelectorList,)),
        _Field('ref', (ct.SelectorList,)),
        _Field('str_or_none'),
        _Field('ref_tuple', (ct.SelectorContains,)),
        _Field('ref_tuple', (ct.SelectorLang,)),
        _Field('int'),
    ),
}

# Fixed top-level keys of a version 1 document.
_TOP_KEYS = frozenset(('version', 'root', 'nodes', 'namespaces', 'custom', 'flags', 'pattern'))

# Required top-level keys of a version 1 document.
_REQUIRED_KEYS = frozenset(('version', 'root', 'nodes'))

# Lookup from an immutable class to its fixed node type name.
_TYPE_NAMES: dict[type[ct.Immutable], str] = {spec.cls: name for name, spec in _SPECS.items()}


def _flatten(roots: list[ct.Immutable]) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """
    Flatten immutable objects into a table of JSON nodes, children before parents.

    Objects are deduplicated by identity, so a sub-structure shared between several parents
    is stored once and referenced by index. The ordering guarantees every reference points
    backwards, which keeps the table acyclic.
    """

    indexes: dict[int, int] = {}
    nodes: list[dict[str, Any]] = []
    stack: list[tuple[ct.Immutable, list[Any] | None]] = [(root, None) for root in reversed(roots)]

    while stack:
        obj, values = stack.pop()
        obj_id = id(obj)
        if obj_id in indexes:
            continue

        if values is None:
            slots = list(obj.__slots__[:-1])
            values = [getattr(obj, slot) for slot in slots]
            stack.append((obj, values))
            for value in values:
                if isinstance(value, ct.Immutable):
                    stack.append((value, None))
                elif value.__class__ is tuple:
                    stack.extend((item, None) for item in value if isinstance(item, ct.Immutable))
            continue

        node_type = _TYPE_NAMES[type(obj)]
        spec = _SPECS[node_type]
        encoded: list[Any] = []
        for index, field in enumerate(spec.fields):
            value = values[index]
            if field.kind in ('ref', 'ref_or_none'):
                values[index] = None if value is None else indexes[id(value)]
            elif field.kind == 'ref_tuple':
                items = list(value)
                for item_index, item in enumerate(items):
                    if item is ct.Null:
                        items[item_index] = None
                    elif isinstance(item, ct.Immutable):
                        items[item_index] = indexes[id(item)]
                values[index] = items
            else:
                values[index] = _ENCODERS[field.kind](value)
            encoded.append(values[index])

        indexes[obj_id] = len(nodes)
        nodes.append({'type': node_type, 'fields': encoded})

    return nodes, indexes


def graph_to_json(sieve: cm.SoupSieve, *, indent: int | None = None) -> str:
    """
    Serialize a compiled selector to a versioned JSON document.

    The exported document contains the compiled selector graph, the namespace map, the
    expanded custom selector aliases and the match flags. The original pattern is included
    for diagnostics only.
    """

    roots: list[ct.Immutable] = [sieve.selectors]
    if sieve.custom is not None:
        roots.extend(sieve.custom[key] for key in sorted(sieve.custom))
    nodes, indexes = _flatten(roots)

    custom: dict[str, int] | None = None
    if sieve.custom is not None:
        custom = {key: indexes[id(sieve.custom[key])] for key in sorted(sieve.custom)}

    document = {
        'version': GRAPH_VERSION,
        'root': indexes[id(sieve.selectors)],
        'nodes': nodes,
        'namespaces': None if sieve.namespaces is None else dict(sieve.namespaces),
        'custom': custom,
        'flags': sieve.flags,
        'pattern': sieve.pattern,
    }
    return json.dumps(document, indent=indent)


def _error(message: str) -> GraphFormatError:
    """Build a format error with a consistent prefix."""

    return GraphFormatError(f'Invalid selector graph: {message}')


def _check_type(value: Any, expected: type | tuple[type, ...], label: str) -> None:
    """Check that a value has exactly the expected JSON-backed type."""

    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        names = expected if isinstance(expected, tuple) else (expected,)
        name = ', '.join(kind.__name__ for kind in names)
        raise _error(f'{label} must be {name}, got {type(value).__name__}')


def _check_ref(
    value: Any,
    targets: tuple[type[ct.Immutable], ...],
    node_index: int,
    nodes: list[dict[str, Any]],
    label: str,
    *,
    allow_none: bool
) -> None:
    """Validate an index reference, including its target type and the no-cycle ordering."""

    if value is None:
        if allow_none:
            return
        raise _error(f'{label} must not be null')
    _check_type(value, int, label)
    if value >= node_index:
        # References may only point at earlier nodes, so a cycle or a forward reference fails
        # before any object could be constructed.
        raise _error(f'{label} references node {value}, which is not an earlier node')
    if not 0 <= value < len(nodes):
        raise _error(f'{label} references node {value}, which is outside the node table')
    target_name = nodes[value]['type']
    allowed = {_TYPE_NAMES[target] for target in targets}
    if target_name not in allowed:
        raise _error(f'{label} references a {target_name} node, expected one of {sorted(allowed)}')


def _compile_pattern(value: Any, label: str) -> re.Pattern[str]:
    """Rebuild a compiled regex from stored pattern data without touching the original CSS."""

    try:
        # Attribute value patterns are always compiled with `re.DOTALL` by the parser.
        return re.compile(value, re.DOTALL)
    except re.error as exc:
        raise _error(f'{label} contains an invalid regular expression: {exc}') from exc


def _validate_field(
    field: _Field,
    value: Any,
    node_index: int,
    nodes: list[dict[str, Any]],
    label: str
) -> None:
    """Validate one field of one node against its fixed specification."""

    kind = field.kind
    if kind == 'str' or kind == 'str_or_none':
        if value is not None or kind == 'str':
            _check_type(value, str, label)
    elif kind == 'bool':
        _check_type(value, bool, label)
    elif kind == 'int':
        _check_type(value, int, label)
    elif kind == 'str_tuple':
        _check_type(value, list, label)
        for item_index, item in enumerate(value):
            _check_type(item, str, f'{label}[{item_index}]')
    elif kind == 'pattern':
        if value is not None:
            _check_type(value, str, label)
    elif kind == 'ref':
        _check_ref(value, field.targets, node_index, nodes, label, allow_none=False)
    elif kind == 'ref_or_none':
        _check_ref(value, field.targets, node_index, nodes, label, allow_none=True)
    elif kind == 'ref_tuple':
        _check_type(value, list, label)
        for item_index, item in enumerate(value):
            _check_ref(
                item,
                field.targets,
                node_index,
                nodes,
                f'{label}[{item_index}]',
                allow_none=field.nullable_items
            )
    else:  # pragma: no cover
        raise _error(f'unknown field kind {kind!r}')


def _validate_nodes(raw_nodes: Any) -> list[dict[str, Any]]:
    """Validate the whole node table and pre-compile stored regex pattern data."""

    _check_type(raw_nodes, list, 'nodes')
    if len(raw_nodes) > GRAPH_NODE_LIMIT:
        raise _error(f'node table exceeds the limit of {GRAPH_NODE_LIMIT} nodes')
    if not raw_nodes:
        raise _error('node table must not be empty')

    nodes: list[dict[str, Any]] = []
    for node_index, raw_node in enumerate(raw_nodes):
        label = f'nodes[{node_index}]'
        _check_type(raw_node, dict, label)
        if set(raw_node) != {'type', 'fields'}:
            raise _error(f'{label} must contain exactly the keys type and fields')
        node_type = raw_node['type']
        _check_type(node_type, str, f'{label}.type')
        if node_type not in _SPECS:
            raise _error(f'{label}.type {node_type!r} is not a supported node type')
        spec = _SPECS[node_type]
        fields = raw_node['fields']
        _check_type(fields, list, f'{label}.fields')
        if len(fields) != len(spec.fields):
            raise _error(f'{label}.fields must contain {len(spec.fields)} values for {node_type}')

        validated_fields: list[Any] = []
        for field_index, (field, value) in enumerate(zip(spec.fields, fields, strict=True)):
            field_label = f'{label}.fields[{field_index}]'
            _validate_field(field, value, node_index, nodes, field_label)
            if field.kind == 'pattern' and value is not None:
                value = _compile_pattern(value, field_label)
            validated_fields.append(value)
        nodes.append({'type': node_type, 'fields': validated_fields})

    return nodes


def _validate_namespaces(value: Any) -> ct.Namespaces | None:
    """Validate and build the namespace map."""

    if value is None:
        return None
    _check_type(value, dict, 'namespaces')
    for key, item in value.items():
        _check_type(key, str, 'namespaces key')
        _check_type(item, str, f'namespaces[{key!r}]')
    return ct.Namespaces(value)


def _validate_custom(
    value: Any,
    nodes: list[dict[str, Any]]
) -> dict[str, int]:
    """Validate the custom selector map, including alias names and list references."""

    if value is None:
        return {}
    _check_type(value, dict, 'custom')
    refs: dict[str, int] = {}
    seen: set[str] = set()
    for key, ref in value.items():
        _check_type(key, str, 'custom key')
        # Keys are stored normalized, but normalize again so validation does not trust that.
        normalized = util.lower(cp.css_unescape(key))
        if normalized in seen:
            raise _error(f'custom selector {normalized!r} is defined twice')
        if cp.RE_CUSTOM.match(normalized) is None:
            raise _error(f'{normalized!r} is not a valid custom pseudo-class name')
        seen.add(normalized)
        _check_ref(ref, (ct.SelectorList,), len(nodes), nodes, f'custom[{key!r}]', allow_none=False)
        refs[normalized] = ref
    return refs


def _build_nodes(nodes: list[dict[str, Any]]) -> list[ct.Immutable]:
    """Construct immutable nodes from a fully validated table."""

    objects: list[ct.Immutable] = []
    for node in nodes:
        spec = _SPECS[node['type']]
        values = list(node['fields'])
        for field_index, field in enumerate(spec.fields):
            if field.kind in ('ref', 'ref_or_none'):
                ref = values[field_index]
                if ref is not None:
                    values[field_index] = objects[ref]
            elif field.kind == 'ref_tuple':
                if field.nullable_items:
                    values[field_index] = tuple(
                        ct.Null if ref is None else objects[ref] for ref in values[field_index]
                    )
                else:
                    values[field_index] = tuple(objects[ref] for ref in values[field_index])
            elif field.kind == 'str_tuple':
                values[field_index] = tuple(values[field_index])
        objects.append(spec.cls(*values))
    return objects


def graph_from_json(document: str | bytes) -> cm.SoupSieve:
    """
    Rebuild a compiled selector from a versioned JSON document.

    The whole document is validated before any selector node is constructed, and therefore
    before any DOM traversal could take place. Neither arbitrary Python classes nor the
    original CSS text are used to rebuild the graph.
    """

    if not isinstance(document, (str, bytes)):
        raise _error(f'document must be str or bytes, got {type(document).__name__}')
    try:
        raw = json.loads(document)
    except json.JSONDecodeError as exc:
        raise _error(f'document is not valid JSON: {exc}') from exc

    _check_type(raw, dict, 'document')
    extra = set(raw) - _TOP_KEYS
    if extra:
        raise _error(f'unknown top-level fields: {sorted(extra)}')
    missing = _REQUIRED_KEYS - set(raw)
    if missing:
        raise _error(f'missing required top-level fields: {sorted(missing)}')

    version = raw['version']
    _check_type(version, int, 'version')
    if version != GRAPH_VERSION:
        raise _error(f'unsupported graph version {version}, expected {GRAPH_VERSION}')

    nodes = _validate_nodes(raw['nodes'])
    _check_ref(raw['root'], (ct.SelectorList,), len(nodes), nodes, 'root', allow_none=False)

    namespaces = _validate_namespaces(raw.get('namespaces'))
    custom_refs = _validate_custom(raw.get('custom'), nodes)

    flags = raw.get('flags', 0)
    _check_type(flags, int, 'flags')
    if flags < 0:
        raise _error('flags must not be negative')

    pattern = raw.get('pattern', '')
    _check_type(pattern, str, 'pattern')

    objects = _build_nodes(nodes)
    root = objects[raw['root']]
    assert isinstance(root, ct.SelectorList)

    custom = None
    if custom_refs:
        # The alias values are already compiled selector lists, so the constructor only
        # validates names and never recompiles CSS text.
        custom_values = {
            key: cast('ct.SelectorList', objects[ref]) for key, ref in custom_refs.items()
        }
        custom = ct.CustomSelectors(custom_values)

    return cm.SoupSieve(pattern, root, namespaces, custom, flags)
