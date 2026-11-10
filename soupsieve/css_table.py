"""
HTML table logical column support.

Implements the table processing model from the HTML specification so that the CSS column
combinator (`||`) and the `:nth-col()` / `:nth-last-col()` pseudo-classes can resolve the
logical columns covered by a cell without relying on a rendered layout.

The calculated structures are derived data held outside of the Beautiful Soup tree, which is
never modified. Nested tables are modeled independently: a cell only ever belongs to the
nearest ancestor table, and a nested table's grid does not affect the table that contains it.
"""
from __future__ import annotations
import re
from typing import Iterator
import bs4

# The HTML specification limits `colspan`, `rowspan`, and `span` values to 1000.
MAX_SPAN = 1000

# Elements that establish a row group for a `rowspan="0"` cell.
ROW_GROUPS = ('thead', 'tbody', 'tfoot')

# Elements that are table cells.
CELL_TAGS = ('td', 'th')

RE_DIGITS = re.compile(r'[0-9]+')


def parse_span(el: bs4.Tag, attribute: str, default: int = 1) -> int:
    """
    Parse a non-negative integer span attribute following the HTML specification.

    A missing, non-numeric, zero, or otherwise invalid value is normalized to `default`, and a
    value greater than the allowed maximum is clamped to it. Floating point and signed values
    are invalid as the attributes only accept non-negative integer literals.
    """

    value = el.get(attribute)
    if value is None or isinstance(value, list):
        return default
    match = RE_DIGITS.fullmatch(str(value).strip())
    if match is None:
        return default
    span = int(match.group(0))
    if span == 0:
        return default
    if span > MAX_SPAN:
        return MAX_SPAN
    return span


def get_own_table(el: bs4.Tag) -> bs4.Tag | None:
    """Find the nearest ancestor table that owns the element, ignoring nested tables."""

    parent = el.parent
    while parent is not None:
        if isinstance(parent, bs4.Tag) and parent.name == 'table':
            return parent
        parent = parent.parent
    return None


def is_zero_row_span(cell: bs4.Tag) -> bool:
    """Check whether a cell declares a `rowspan` attribute whose literal value is zero."""

    raw = cell.get('rowspan')
    if raw is None or isinstance(raw, list):
        return False
    match = RE_DIGITS.fullmatch(str(raw).strip())
    return match is not None and int(match.group(0)) == 0


class TableColumnMap:
    """
    Logical column information for a single table.

    `cell_columns` maps a cell to the 1-based logical columns it covers. `column_elements` and
    `column_cells` map each 1-based logical column to the `col` elements that declare it and the
    cells that cover it, respectively. `column_count` is the total number of logical columns.
    """

    __slots__ = ('table', 'cell_columns', 'column_elements', 'column_cells', 'column_count')

    def __init__(self, table: bs4.Tag) -> None:
        """Initialize."""

        self.table = table
        self.cell_columns: dict[int, tuple[int, ...]] = {}
        self.column_elements: dict[int, list[bs4.Tag]] = {}
        self.column_cells: dict[int, list[bs4.Tag]] = {}
        self.column_count = self._build()

    def _own_rows(self) -> list[bs4.Tag]:
        """Collect the table's own rows in document order, excluding rows in nested tables."""

        return [row for row in self.table.find_all('tr') if get_own_table(row) is self.table]

    def _row_cells(self, row: bs4.Tag) -> list[bs4.Tag]:
        """Collect a row's own cells in document order, excluding cells in nested tables."""

        return [cell for cell in row.find_all(CELL_TAGS) if get_own_table(cell) is self.table]

    def _register_col(self, col: bs4.Tag, start: int, end: int) -> None:
        """Associate a `col` or `colgroup` element with each logical column it declares."""

        for column in range(start, end + 1):
            self.column_elements.setdefault(column, []).append(col)

    def _build_declared_columns(self) -> int:
        """Count the logical columns declared by the table's `col` and `colgroup` elements."""

        declared = 0
        for group in self.table.find_all('colgroup'):
            if get_own_table(group) is not self.table:
                continue
            cols = [child for child in group.children if isinstance(child, bs4.Tag) and child.name == 'col']
            if cols:
                for col in cols:
                    start = declared + 1
                    declared += parse_span(col, 'span')
                    self._register_col(col, start, declared)
            else:
                start = declared + 1
                declared += parse_span(group, 'span')
                self._register_col(group, start, declared)
        # A `col` may be a direct child of a table when no `colgroup` wraps it.
        for child in self.table.children:
            if isinstance(child, bs4.Tag) and child.name == 'col' and get_own_table(child) is self.table:
                start = declared + 1
                declared += parse_span(child, 'span')
                self._register_col(child, start, declared)
        return declared

    def _row_group_end(self, rows: list[bs4.Tag], index: int) -> int:
        """Return the index of the last row in the row group that contains the given row."""

        row = rows[index]
        parent = row.parent
        if isinstance(parent, bs4.Tag) and parent.name in ROW_GROUPS and get_own_table(parent) is self.table:
            group_key = id(parent)
        else:
            group_key = id(self.table)
        end = index
        for candidate in range(index + 1, len(rows)):
            candidate_parent = rows[candidate].parent
            if isinstance(candidate_parent, bs4.Tag) and candidate_parent.name in ROW_GROUPS:
                candidate_key = (
                    id(candidate_parent) if get_own_table(candidate_parent) is self.table else None
                )
            else:
                candidate_key = id(self.table)
            if candidate_key == group_key:
                end = candidate
        return end

    def _build(self) -> int:
        """Run the table grid processing algorithm and return the total logical column count."""

        declared = self._build_declared_columns()
        rows = self._own_rows()

        # Number of rows a column slot stays occupied, including the current row, keyed by column.
        active: dict[int, int] = {}
        # Cells with `rowspan="0"` as `(cell, row index, first column, end column)`.
        zero_spans: list[tuple[bs4.Tag, int, int, int]] = []
        # Slots claimed by `rowspan="0"` cells, keyed by `(row index, column index)`.
        zero_grid: set[tuple[int, int]] = set()
        width = 0

        for row_index, row in enumerate(rows):
            # Expire row spans whose final row was the previous one.
            for column in [key for key, remaining in active.items() if remaining == 1]:
                del active[column]
            for column in active:
                active[column] -= 1

            column_index = 0
            for cell in self._row_cells(row):
                colspan = parse_span(cell, 'colspan')
                rowspan = parse_span(cell, 'rowspan')

                # Advance to the first slot not claimed by an earlier cell, an active span, or a zero row span.
                while column_index in active or (row_index, column_index) in zero_grid:
                    column_index += 1

                start = column_index
                end = column_index + colspan
                columns = tuple(range(start + 1, end + 1))
                self.cell_columns[id(cell)] = columns
                for column in columns:
                    self.column_cells.setdefault(column, []).append(cell)

                if is_zero_row_span(cell):
                    zero_spans.append((cell, row_index, start, end))
                    for column in range(start, end):
                        zero_grid.add((row_index, column))
                elif rowspan > 1:
                    # Reserve the covered columns for the spanned rows, including the current row.
                    for column in range(start, end):
                        active[column] = max(active.get(column, 0), rowspan)

                column_index = end
                width = max(width, end)

            # A row span may extend past every cell on this row while still occupying a grid column.
            width = max(width, max(active.keys(), default=-1) + 1)

        # Expand `rowspan="0"` cells through the remainder of their row group.
        for cell, row_index, start, end in zero_spans:
            group_end = self._row_group_end(rows, row_index)
            for later_row in range(row_index + 1, group_end + 1):
                if all((later_row, column) not in zero_grid for column in range(start, end)):
                    for column in range(start, end):
                        zero_grid.add((later_row, column))

        return max(declared, width)

    def get_columns(self, cell: bs4.Tag) -> tuple[int, ...]:
        """Get the 1-based logical columns covered by a cell, or an empty tuple for non-cells."""

        if cell.name not in CELL_TAGS or get_own_table(cell) is not self.table:
            return ()
        return self.cell_columns.get(id(cell), ())

    def column_members(self, cell: bs4.Tag) -> Iterator[bs4.Tag]:
        """Yield the `col` elements and sibling cells sharing any logical column with a cell."""

        seen: set[int] = set()
        for column in self.get_columns(cell):
            for col in self.column_elements.get(column, ()):
                if id(col) not in seen:
                    seen.add(id(col))
                    yield col
            for other in self.column_cells.get(column, ()):
                if other is not cell and id(other) not in seen:
                    seen.add(id(other))
                    yield other


class TableTracker:
    """Build and cache the column maps for every table encountered during a match."""

    def __init__(self) -> None:
        """Initialize."""

        self.maps: dict[int, TableColumnMap] = {}

    def reset(self) -> None:
        """Reset."""

        self.maps.clear()

    def get_map(self, table: bs4.Tag) -> TableColumnMap:
        """Get the cached column map for a table, building it on first use."""

        key = id(table)
        table_map = self.maps.get(key)
        if table_map is None:
            table_map = TableColumnMap(table)
            self.maps[key] = table_map
        return table_map

    def get_cell_map(self, el: bs4.Tag) -> TableColumnMap | None:
        """Get the column map of the table that owns the element, if it is a table cell."""

        if el.name not in CELL_TAGS:
            return None
        table = get_own_table(el)
        if table is None:
            return None
        return self.get_map(table)

    def get_columns(self, el: bs4.Tag) -> tuple[int, ...]:
        """Get the 1-based logical columns covered by an element that is a table cell."""

        table_map = self.get_cell_map(el)
        if table_map is None:
            return ()
        return table_map.get_columns(el)
