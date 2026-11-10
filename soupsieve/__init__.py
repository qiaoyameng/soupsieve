"""
Soup Sieve.

A CSS selector filter for BeautifulSoup4.

MIT License

Copyright (c) 2018 Isaac Muse

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations
from .__meta__ import __version__, __version_info__  # noqa: F401
from . import css_parser as cp
from . import css_match as cm
from . import css_types as ct
from .util import DEBUG, NOCACHE, NOSTRICT, SelectorSyntaxError  # noqa: F401
import bs4
from typing import Any, Mapping, Iterator, Iterable, cast

__all__ = (
    'DEBUG', 'NOCACHE', 'NOSTRICT', 'SelectorSyntaxError', 'CustomSelectors', 'SoupSieve',
    'closest', 'compile', 'filter', 'iselect', 'match', 'select', 'select_many', 'select_one'
)

SoupSieve = cm.SoupSieve
CustomSelectors = ct.CustomSelectors


def compile(  # noqa: A001
    pattern: str,
    namespaces: dict[str, str] | None = None,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> cm.SoupSieve:
    """Compile CSS pattern."""

    if isinstance(pattern, SoupSieve):
        if flags:
            raise ValueError("Cannot process 'flags' argument on a compiled selector list")
        elif namespaces is not None:
            raise ValueError("Cannot process 'namespaces' argument on a compiled selector list")
        elif custom is not None:
            raise ValueError("Cannot process 'custom' argument on a compiled selector list")
        return pattern

    return cp._cached_css_compile(
        pattern,
        ct.Namespaces(namespaces) if namespaces is not None else namespaces,
        ct.CustomSelectors(
            cast('dict[str, str | ct.SelectorList]', custom), max_selectors=max_selectors
        ) if custom is not None and not isinstance(custom, ct.CustomSelectors) else custom,
        tuple(i.lower() for i in ignore) if ignore is not None else ignore,
        flags,
        max_selectors
    )


def purge() -> None:
    """Purge cached patterns."""

    cp._purge_cache()


def closest(
    select: str,
    tag: bs4.Tag,
    namespaces: dict[str, str] | None = None,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> bs4.Tag | None:
    """Match closest ancestor."""

    return compile(
        select,
        namespaces,
        flags,
        custom=custom,
        ignore=ignore,
        max_selectors=max_selectors,
        **kwargs
    ).closest(tag)


def match(
    select: str,
    tag: bs4.Tag,
    namespaces: dict[str, str] | None = None,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> bool:
    """Match node."""

    return compile(
        select,
        namespaces,
        flags,
        custom=custom,
        ignore=ignore,
        max_selectors=max_selectors,
        **kwargs
    ).match(tag)


def filter(  # noqa: A001
    select: str,
    iterable: Iterable[bs4.Tag],
    namespaces: dict[str, str] | None = None,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> list[bs4.Tag]:
    """Filter list of nodes."""

    return compile(
        select,
        namespaces,
        flags,
        custom=custom,
        ignore=ignore,
        max_selectors=max_selectors,
        **kwargs
    ).filter(iterable)


def select_one(
    select: str,
    tag: bs4.Tag,
    namespaces: dict[str, str] | None = None,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> bs4.Tag | None:
    """Select a single tag."""

    return compile(
        select,
        namespaces,
        flags,
        custom=custom,
        ignore=ignore,
        max_selectors=max_selectors,
        **kwargs
    ).select_one(tag)


def select(
    select: str,
    tag: bs4.Tag,
    namespaces: dict[str, str] | None = None,
    limit: int = 0,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> list[bs4.Tag]:
    """Select the specified tags."""

    return compile(
        select,
        namespaces,
        flags,
        custom=custom,
        ignore=ignore,
        max_selectors=max_selectors,
        **kwargs
    ).select(tag, limit)


def iselect(
    select: str,
    tag: bs4.Tag,
    namespaces: dict[str, str] | None = None,
    limit: int = 0,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> Iterator[bs4.Tag]:
    """Iterate the specified tags."""

    yield from compile(
        select,
        namespaces,
        flags,
        custom=custom,
        ignore=ignore,
        max_selectors=max_selectors,
        **kwargs
    ).iselect(tag, limit)


def select_many(
    selects: Mapping[str, str | cm.SoupSieve] | Iterable[tuple[str, str | cm.SoupSieve]],
    tag: bs4.Tag,
    namespaces: dict[str, str] | None = None,
    limits: Mapping[str, int] | None = None,
    flags: int = 0,
    *,
    custom: Mapping[str, str | ct.SelectorList] | None = None,
    ignore: Iterable[str] | None = None,
    max_selectors: int = cp.SELECTOR_LIMIT,
    **kwargs: Any
) -> dict[str, list[bs4.Tag]]:
    """
    Select tags for many named selectors in a single document order traversal.

    `selects` maps a rule name to a CSS selector string or a compiled `SoupSieve` object.
    Compiled rules keep their own namespaces, custom selectors, and flags; string rules are
    compiled with the shared `namespaces`, `custom`, `ignore`, `flags`, and `max_selectors`
    arguments. `limits` optionally maps a rule name to a positive integer limit (0, the default,
    means no limit); each rule stops collecting once its own limit is reached, and the traversal
    stops as soon as every rule has reached its limit.

    Returns a dictionary mapping each rule name to its matched tags, in document order.
    A tag matching multiple rules appears in each of those rules' results, but never twice
    within a single rule's results.

    All rules are compiled before the traversal begins, so a compilation failure is reported
    with the offending rule's name and no partial results are delivered.
    """

    items = list(selects.items()) if isinstance(selects, Mapping) else list(selects)

    names: list[str] = []
    patterns: list[str | cm.SoupSieve] = []
    seen: set[str] = set()
    for name, pattern in items:
        if name in seen:
            raise ValueError(f"Duplicate rule name {name!r}")
        seen.add(name)
        names.append(name)
        patterns.append(pattern)

    if limits is None:
        limits = {}
    else:
        unknown = [name for name in limits if name not in seen]
        if unknown:
            raise ValueError(f"Limit specified for unknown rule {unknown[0]!r}")

    # Compile every rule up front so that a failure is reported with its rule
    # name before any node is visited and no partial results are delivered.
    compiled: list[cm.SoupSieve] = []
    for name, pattern in zip(names, patterns):
        if isinstance(pattern, cm.SoupSieve):
            # Compiled rules are self-contained and keep their own namespaces,
            # custom selectors, and flags.
            compiled.append(pattern)
            continue
        try:
            compiled.append(compile(
                pattern,
                namespaces,
                flags,
                custom=custom,
                ignore=ignore,
                max_selectors=max_selectors,
                **kwargs
            ))
        except SelectorSyntaxError as e:
            raise SelectorSyntaxError(f"Rule {name!r}: {e}") from e

    if not compiled:
        return {}

    # Combine flags (a `NOCACHE` rule disables structural caching for the shared
    # traversal) and evaluate each rule with its own selectors and namespaces.
    combined_flags = 0
    rules: list[tuple[ct.SelectorList, ct.Namespaces | dict[str, str], int]] = []
    for name, selector in zip(names, compiled):
        combined_flags |= selector.flags
        rules.append((
            selector.selectors,
            selector.namespaces if selector.namespaces is not None else {},
            limits.get(name, 0)
        ))

    matcher = cm.CSSMatch(compiled[0].selectors, tag, None, combined_flags)
    return dict(zip(names, matcher.select_many(rules)))


def escape(ident: str) -> str:
    """Escape identifier."""

    return cp.escape(ident)
