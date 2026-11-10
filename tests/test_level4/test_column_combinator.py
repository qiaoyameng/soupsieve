"""Test the CSS column combinator `||`."""
from .. import util
from soupsieve import SelectorSyntaxError


class TestColumnCombinator(util.TestCase):
    """Test the column combinator on a three column table with a two row merged cell."""

    MARKUP = """
    <table id="t">
    <colgroup><col id="c1"><col id="c2" span="2"></colgroup>
    <tr id="r1">
    <td id="0" rowspan="2">A</td>
    <td id="1">B</td>
    <td id="2" class="price">C</td>
    </tr>
    <tr id="r2">
    <td id="3" colspan="2">D</td>
    </tr>
    </table>
    """

    def test_col_to_cells(self):
        """Test a `col` matches every cell covering one of its declared logical columns."""

        self.assert_selector(self.MARKUP, "col || td", ["0", "1", "2", "3"], flags=util.HTML)

    def test_spanned_col_to_cells(self):
        """Test a `col` with a span declares several columns and matches all their cells."""

        self.assert_selector(self.MARKUP, "col#c2 || td", ["1", "2", "3"], flags=util.HTML)

    def test_cell_to_cell(self):
        """Test a cell matches the other cells sharing a logical column."""

        self.assert_selector(self.MARKUP, "td || td", ["1", "2", "3"], flags=util.HTML)

    def test_no_whitespace(self):
        """Test the combinator works without surrounding whitespace."""

        self.assert_selector(self.MARKUP, "col||td", ["0", "1", "2", "3"], flags=util.HTML)

    def test_combine_with_attribute_and_pseudo(self):
        """Test combining the column relation with other selector machinery."""

        self.assert_selector(
            self.MARKUP,
            "col#c2 || td[class='price']",
            ["2"],
            flags=util.HTML
        )
        self.assert_selector(
            self.MARKUP,
            ":is(col) || td:nth-col(3)",
            ["2", "3"],
            flags=util.HTML
        )

    def test_not(self):
        """Test the column combinator works through a `:not()` selector list."""

        self.assert_selector(
            self.MARKUP,
            "td:not(col#c1 || td)",
            ["1", "2", "3"],
            flags=util.HTML
        )

    def test_has(self):
        """Test the column combinator works as a forward looking `:has()` relation."""

        self.assert_selector(self.MARKUP, "table:has(td || td)", ["t"], flags=util.HTML)

    def test_syntax_errors(self):
        """Test a dangling or doubled column combinator is a syntax error."""

        for selector in ("td ||", "|| td", "td || || th", ":not(td ||)"):
            self.assert_raises(selector, SelectorSyntaxError)


class TestColumnCombinatorNested(util.TestCase):
    """Test the column combinator keeps nested tables isolated."""

    MARKUP = """
    <table id="outer">
    <tr>
    <td id="0">outer-a</td>
    <td id="1">
    <table id="inner">
    <tr><td id="2">in-a</td><td id="3">in-b</td><td id="4">in-c</td></tr>
    <tr><td id="5">in-d</td><td id="6">in-e</td><td id="7">in-f</td></tr>
    </table>
    </td>
    </tr>
    </table>
    """

    def test_nested_partner_not_shared(self):
        """Test each table resolves column partners inside its own grid only."""

        # The outer table's own cells do not share a column, so restricting to the outer table's
        # direct row cells yields no column partners even though a nested table lives in one cell.
        self.assert_selector(self.MARKUP, "#outer > tr > td || td", [], flags=util.HTML)
        # The nested table has its own independent two row grid with shared columns.
        self.assert_selector(
            self.MARKUP,
            "#inner td || td",
            ["2", "3", "4", "5", "6", "7"],
            flags=util.HTML
        )
