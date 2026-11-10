"""Test logical column resolution driven by `col` and `colgroup` declarations."""
from .. import util


class TestColumnDeclarations(util.TestCase):
    """Test column counts and `col` association come from declarations as well as the grid."""

    MARKUP = """
    <table>
    <colgroup><col id="c1"><col id="c2" span="2"></colgroup>
    <tr><td id="0">A</td><td id="1">B</td></tr>
    </table>
    """

    def test_declared_columns_extend_implicit_grid(self):
        """Test a `col` span declares columns beyond those implied by the cells."""

        from soupsieve.css_table import TableColumnMap

        soup = self.soup(self.MARKUP, 'html.parser')
        table_map = TableColumnMap(soup.table)
        # The grid only has two cells, but the `col` span declares three logical columns.
        self.assertEqual(table_map.column_count, 3)
        self.assertEqual(table_map.get_columns(soup.find(id="0")), (1,))
        self.assertEqual(table_map.get_columns(soup.find(id="1")), (2,))

    def test_spanned_col_matches_cells_by_declared_column(self):
        """Test a `col` with a span reaches cells through the columns it declares."""

        # `c2` declares columns two and three; the only cell on column two is `1`.
        self.assert_selector(self.MARKUP, "col#c2 || td", ["1"], flags=util.PYHTML)


class TestColumnCombinatorHas(util.TestCase):
    """Test the column combinator as a `:has()` relation."""

    MARKUP = """
    <table id="t">
    <tr id="r1"><td id="0">A</td><td id="1">B</td></tr>
    <tr id="r2"><td id="2">C</td><td id="3">D</td></tr>
    </table>
    """

    def test_has_column_relation(self):
        """Test a table matches when it contains cells sharing a logical column."""

        self.assert_selector(self.MARKUP, "table:has(td || td)", ["t"], flags=util.PYHTML)

    def test_has_nth_col_relation(self):
        """Test `:nth-col()` inside `:has()` finds rows with a cell on that column."""

        self.assert_selector(self.MARKUP, "tr:has(td:nth-col(2))", ["r1", "r2"], flags=util.PYHTML)
