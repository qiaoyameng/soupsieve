"""Test selecting many named rules in a single traversal."""
from unittest import mock
import soupsieve as sv
from soupsieve import css_match as cm
from .. import util

XHTML = 'http://www.w3.org/1999/xhtml'
SVG = 'http://www.w3.org/2000/svg'


def count_descendant_visits(func, *args, **kwargs):
    """Run `func` and count the nodes yielded by the shared descendant traversal."""

    original = cm.CSSMatch.get_tag_descendants
    visits = [0]

    def counting(self, el, template_contents=False):
        for node in original(self, el, template_contents=template_contents):
            visits[0] += 1
            yield node

    with mock.patch.object(cm.CSSMatch, 'get_tag_descendants', counting):
        result = func(*args, **kwargs)
    return result, visits[0]


class TestSelectMany(util.TestCase):
    """Test `select_many`."""

    MARKUP = """
    <html>
    <head></head>
    <body>
    <div id="a" class="box">
        <p id="p1">one</p>
        <p id="p2">two</p>
        <span id="s1">span</span>
    </div>
    <div id="b" class="box">
        <p id="p3">three</p>
    </div>
    <div id="c">
        <p id="p4">four</p>
    </div>
    <ul id="list">
        <li id="l1">1</li>
        <li id="l2">2</li>
        <li id="l3">3</li>
        <li id="l4">4</li>
    </ul>
    <template id="t"><p id="tp">templated</p></template>
    </body>
    </html>
    """

    def soup_namespaced(self):
        """Get a soup with namespace aware tags."""

        soup = self.soup(self.MARKUP, 'html.parser')
        for tag in soup.find_all(['html', 'head', 'body', 'div', 'p', 'span', 'ul', 'li']):
            tag.namespace = XHTML
        svg = soup.new_tag('svg', namespace=SVG, nsprefix='svg')
        rect = soup.new_tag('rect', namespace=SVG, nsprefix='svg')
        rect['id'] = 'r1'
        svg.append(rect)
        soup.body.append(svg)
        return soup

    def test_differential(self):
        """Ensure `select_many` matches individual `select` calls for `nth`, `:has`, and namespaces."""

        soup = self.soup_namespaced()
        rules = {
            'nth': 'li:nth-child(2n)',
            'nth-of-type': 'p:nth-of-type(2)',
            'has': 'div:has(> span)',
            'scope': ':scope > body > div',
            'ns': sv.compile('svg|rect', namespaces={'svg': SVG}),
            'ns-html': sv.compile('html|p', namespaces={'html': XHTML}),
            'custom': sv.compile('p:--multiword', custom={':--multiword': '[id="p2"], [id="p3"]'}),
            'nocache': sv.compile('li:nth-child(2n + 1)', flags=sv.NOCACHE),
            'plain': 'div.box'
        }
        limits = {'plain': 1, 'ns-html': 2}

        results = sv.select_many(rules, soup, limits=limits)

        self.assertEqual(list(results), list(rules))
        for name, rule in rules.items():
            limit = limits.get(name, 0)
            if isinstance(rule, str):
                expected = sv.select(rule, soup, limit=limit)
            else:
                expected = rule.select(soup, limit=limit)
            self.assertEqual(expected, results[name], name)

        # Spot check a few to ensure the test is meaningful.
        self.assertEqual(['l2', 'l4'], [el['id'] for el in results['nth']])
        self.assertEqual(['a'], [el['id'] for el in results['has']])
        self.assertEqual(['r1'], [el['id'] for el in results['ns']])
        self.assertEqual(['p2', 'p3'], [el['id'] for el in results['custom']])

    def test_limit(self):
        """Ensure each rule honors its own limit and stops collecting independently."""

        soup = self.soup(self.MARKUP, 'html.parser')
        results = sv.select_many(
            {
                'one': 'p',
                'two': 'p',
                'all': 'p',
                'none': 'p'
            },
            soup,
            limits={'one': 1, 'two': 2, 'none': 0}
        )

        self.assertEqual(['p1'], [el['id'] for el in results['one']])
        self.assertEqual(['p1', 'p2'], [el['id'] for el in results['two']])
        self.assertEqual(['p1', 'p2', 'p3', 'p4'], [el['id'] for el in results['all']])
        self.assertEqual(['p1', 'p2', 'p3', 'p4'], [el['id'] for el in results['none']])

    def test_multi_match_no_duplicates(self):
        """Ensure a tag matching many rules is kept in each, but never duplicated within one."""

        soup = self.soup(self.MARKUP, 'html.parser')
        results = sv.select_many(
            {
                'by-tag': 'div',
                'by-class': '.box',
                'overlapping': 'div, .box, #a'
            },
            soup
        )

        ids = {name: [el.get('id') for el in tags] for name, tags in results.items()}
        self.assertEqual(['a', 'b', 'c'], ids['by-tag'])
        self.assertEqual(['a', 'b'], ids['by-class'])
        self.assertEqual(['a', 'b', 'c'], ids['overlapping'])
        for name, values in ids.items():
            self.assertEqual(len(values), len(set(values)), name)

    def test_shared_traversal(self):
        """Ensure `select_many` walks the tree once instead of once per rule."""

        soup = self.soup(self.MARKUP, 'html.parser')
        rules = {
            'first': 'p',
            'all-divs': 'div',
            'all-spans': 'span',
            'all-lis': 'li'
        }
        limits = {'first': 1}

        _, batched = count_descendant_visits(sv.select_many, rules, soup, limits=limits)

        _, full = count_descendant_visits(sv.select, '*', soup)
        _, first = count_descendant_visits(sv.select, 'p', soup, limit=1)

        individual = 0
        for name, rule in rules.items():
            _, visits = count_descendant_visits(sv.select, rule, soup, limit=limits.get(name, 0))
            individual += visits

        # The batch walks the tree exactly once while the individual selects each walk it again.
        self.assertEqual(full, batched)
        self.assertLess(batched, individual)
        self.assertEqual(first + 3 * full, individual)

    def test_stops_when_all_limits_reached(self):
        """Ensure the traversal stops visiting nodes once every rule has reached its limit."""

        soup = self.soup(self.MARKUP, 'html.parser')
        results, visits = count_descendant_visits(
            sv.select_many,
            {'p1': 'p', 'p2': 'p'},
            soup,
            limits={'p1': 1, 'p2': 2}
        )

        self.assertEqual(['p1'], [el['id'] for el in results['p1']])
        self.assertEqual(['p1', 'p2'], [el['id'] for el in results['p2']])
        # The second `p` is found well before the end of the document.
        self.assertLess(visits, len(soup.find_all(True)))

    def test_template(self):
        """Ensure template contents follow the same rules as a normal select."""

        soup = self.soup(self.MARKUP, 'html.parser')
        rules = {'paras': 'p', 'templated': '#tp'}

        # From the document, template contents are not traversed.
        results = sv.select_many(rules, soup)
        self.assertEqual(sv.select('p', soup), results['paras'])
        self.assertEqual([], results['templated'])

        # From the `template` tag, its contents are reachable.
        template = soup.find('template')
        results = sv.select_many(rules, template)
        self.assertEqual(sv.select('p', template), results['paras'])
        self.assertEqual(['tp'], [el['id'] for el in results['templated']])

    def test_compile_error_reports_name_before_traversal(self):
        """Ensure a bad rule is reported with its name and no traversal or partial results occur."""

        soup = self.soup(self.MARKUP, 'html.parser')
        with mock.patch.object(
            cm.CSSMatch, 'get_tag_descendants', wraps=cm.CSSMatch.get_tag_descendants
        ) as traversal:
            with self.assertRaises(sv.SelectorSyntaxError) as cm_err:
                sv.select_many({'good': 'p', 'bad': 'p > > div'}, soup)

        self.assertIn("'bad'", str(cm_err.exception))
        self.assertEqual(0, traversal.call_count)

    def test_duplicate_names(self):
        """Ensure duplicate rule names are rejected."""

        soup = self.soup(self.MARKUP, 'html.parser')
        with self.assertRaises(ValueError):
            sv.select_many([('a', 'p'), ('a', 'div')], soup)

    def test_unknown_limit(self):
        """Ensure limits for unknown rules are rejected."""

        soup = self.soup(self.MARKUP, 'html.parser')
        with self.assertRaises(ValueError):
            sv.select_many({'a': 'p'}, soup, limits={'b': 1})

    def test_empty(self):
        """Ensure an empty rule set yields an empty result without touching the tag."""

        soup = self.soup(self.MARKUP, 'html.parser')
        self.assertEqual({}, sv.select_many({}, soup))

    def test_iterable_input(self):
        """Ensure rules can be given as an iterable of name/pattern pairs."""

        soup = self.soup(self.MARKUP, 'html.parser')
        results = sv.select_many([('paras', 'p'), ('divs', 'div')], soup, limits={'paras': 2})

        self.assertEqual(['paras', 'divs'], list(results))
        self.assertEqual(sv.select('p', soup, limit=2), results['paras'])
        self.assertEqual(sv.select('div', soup), results['divs'])

    def test_shared_namespaces_default(self):
        """Ensure string rules share the provided namespaces while compiled rules keep their own."""

        soup = self.soup_namespaced()
        results = sv.select_many(
            {
                'shared': 'svg|rect',
                'own': sv.compile('html|p', namespaces={'html': XHTML})
            },
            soup,
            namespaces={'svg': SVG},
            limits={'own': 1}
        )

        self.assertEqual(sv.select('svg|rect', soup, namespaces={'svg': SVG}), results['shared'])
        self.assertEqual(sv.select('html|p', soup, namespaces={'html': XHTML}, limit=1), results['own'])

    def test_detached_scope(self):
        """Ensure `:scope` is evaluated per rule against the context tag."""

        soup = self.soup(self.MARKUP, 'html.parser')
        div = soup.find('div', id='a')
        results = sv.select_many({'scoped': ':scope > p', 'all': 'p'}, div, limits={'all': 1})

        self.assertEqual(sv.select(':scope > p', div), results['scoped'])
        self.assertEqual(sv.select('p', div, limit=1), results['all'])
        self.assertEqual(['p1'], [el['id'] for el in results['all']])
