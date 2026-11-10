"""Test the `:nth-col()` and `:nth-last-col()` pseudo-classes."""
from .. import util
from soupsieve import SelectorSyntaxError


class TestNthCol(util.TestCase):
    """Test logical column pseudo-classes on tables with spans."""

    # A three column table where the first cell spans two rows and the bottom right cell spans two columns.
    MARKUP = """
    <table id="t">
    <colgroup><col id="c1"><col id="c2"><col id="c3"></colgroup>
    <tr id="r1">
    <th id="0" rowspan="2">A</th>
    <td id="1">B</td>
    <td id="2" class="price">C</td>
    </tr>
    <tr id="r2">
    <td id="3" colspan="2">D</td>
    </tr>
    </table>
    """

    def test_nth_col_first(self):
        """Test the first logical column, including a cell with a row span."""

        self.assert_selector(self.MARKUP, "td:nth-col(1), th:nth-col(1)", ["0"], flags=util.HTML)

    def test_nth_col_middle(self):
        """Test a column covered by a cell with a column span."""

        self.assert_selector(self.MARKUP, "td:nth-col(2)", ["1", "3"], flags=util.HTML)

    def test_nth_col_last_index(self):
        """Test the last logical column through `:nth-col()`."""

        self.assert_selector(self.MARKUP, "td:nth-col(3)", ["2", "3"], flags=util.HTML)

    def test_nth_last_col(self):
        """Test `:nth-last-col()` indexes columns from the right."""

        self.assert_selector(self.MARKUP, "td:nth-last-col(1)", ["2", "3"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "td:nth-last-col(2)", ["1", "3"], flags=util.HTML)

    def test_nth_col_formulas(self):
        """Test `An+B`, `even`, and `odd` formulas against covered columns."""

        self.assert_selector(self.MARKUP, "td:nth-col(2n)", ["1", "3"], flags=util.HTML)
        # The `td` cells covering odd numbered columns are column 3, covered by `2` and the spanned `3`.
        self.assert_selector(self.MARKUP, "td:nth-col(odd)", ["2", "3"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "td:nth-col(-n+2)", ["1", "3"], flags=util.HTML)
        self.assert_selector(self.MARKUP, ":is(td, th):nth-col(-n+2)", ["0", "1", "3"], flags=util.HTML)

    def test_nth_col_zero_never_matches(self):
        """Test a constant formula of zero never matches a column."""

        self.assert_selector(self.MARKUP, "td:nth-col(0)", [], flags=util.HTML)

    def test_nth_col_with_attribute_and_pseudo(self):
        """Test combination with attribute selectors, `:is()`, and `:not()`."""

        self.assert_selector(self.MARKUP, "td[class='price']:nth-col(3)", ["2"], flags=util.HTML)
        self.assert_selector(
            self.MARKUP,
            "th:is([rowspan], [colspan]):nth-col(1)",
            ["0"],
            flags=util.HTML
        )
        self.assert_selector(self.MARKUP, "td:not(#\\31 ):nth-col(2)", ["3"], flags=util.HTML)

    def test_nth_col_has(self):
        """Test `:nth-col()` inside a `:has()` relation."""

        # Both rows contain a cell covering the third logical column.
        self.assert_selector(self.MARKUP, "tr:has(td:nth-col(3))", ["r1", "r2"], flags=util.HTML)
        # Both rows also contain a cell covering the second logical column.
        self.assert_selector(self.MARKUP, "tr:has(td:nth-col(2))", ["r1", "r2"], flags=util.HTML)
        # The table itself matches when it contains a cell in the third logical column.
        self.assert_selector(self.MARKUP, "table:has(td:nth-col(3))", ["t"], flags=util.HTML)

    def test_nth_col_non_cell(self):
        """Test elements that are not table cells never match a column pseudo-class."""

        self.assert_selector(self.MARKUP, "col:nth-col(1)", [], flags=util.HTML)
        self.assert_selector(self.MARKUP, "table:nth-col(1)", [], flags=util.HTML)

    def test_nth_col_syntax_errors(self):
        """Test malformed column pseudo-classes are rejected."""

        for selector in (
            ":nth-col()",
            ":nth-col(foo)",
            ":nth-col(+)",
            ":nth-col(2n1)",
            ":nth-last-col()",
            ":nth-col(2n+1 of p)",
            ":nth-col"
        ):
            self.assert_raises(selector, SelectorSyntaxError)


class TestNthColRowSpanZero(util.TestCase):
    """Test `rowspan=\"0\"` handling across row groups."""

    MARKUP = """
    <table>
    <tbody>
    <tr><td id="0" rowspan="0">A</td><td id="1">B</td></tr>
    <tr><td id="2">C</td><td id="3">D</td></tr>
    </tbody>
    <tfoot><tr><td id="4">F</td></tr></tfoot>
    </table>
    """

    def test_rowspan_zero_stops_at_row_group(self):
        """Test a zero row span extends through its row group but not into the footer."""

        self.assert_selector(self.MARKUP, "td:nth-col(1)", ["0", "2", "4"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "tbody td:nth-col(1)", ["0", "2"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "td:nth-col(2)", ["1", "3"], flags=util.HTML)


class TestNthColNestedTable(util.TestCase):
    """Test nested tables keep independent logical column grids."""

    MARKUP = """
    <table id="outer">
    <tr>
    <td id="0">outer</td>
    <td id="1">
    <table id="inner">
    <tr><td id="2">in-a</td><td id="3">in-b</td><td id="4">in-c</td></tr>
    <tr><td id="5">in-d</td><td id="6">in-e</td><td id="7">in-f</td></tr>
    </table>
    </td>
    </tr>
    </table>
    """

    def test_nested_columns_are_isolated(self):
        """Test a nested cell is indexed by the nested table's columns only."""

        self.assert_selector(self.MARKUP, "#inner td:nth-col(1)", ["2", "5"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "#inner td:nth-col(2)", ["3", "6"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "#\\32 :nth-col(2)", [], flags=util.HTML)


class TestNthColInvalidSpans(util.TestCase):
    """Test invalid span attributes follow the HTML normalization rules."""

    MARKUP = """
    <table>
    <tr>
    <td id="0" colspan="abc">A</td>
    <td id="1" colspan="0">B</td>
    <td id="2" colspan="-2">C</td>
    </tr>
    </table>
    """

    def test_invalid_colspan_normalized_to_one(self):
        """Test invalid column spans are treated as a single logical column."""

        self.assert_selector(self.MARKUP, "td:nth-col(1)", ["0"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "td:nth-col(2)", ["1"], flags=util.HTML)
        self.assert_selector(self.MARKUP, "td:nth-col(3)", ["2"], flags=util.HTML)
