"""Test versioned JSON import and export of compiled selector graphs."""
from .. import util
import soupsieve as sv
from soupsieve import css_graph as cg
from soupsieve import css_parser as cp
from soupsieve import css_types as ct
import copy
import json


class TestGraphJSON(util.TestCase):
    """Test the JSON graph document format."""

    MARKUP = """
    <html><body>
    <div id="d1">
      <p id="p1" class="a b" lang="en-US">alpha <span id="s1" class="x">beta</span></p>
      <p id="p2" class="a c" lang="en-GB">gamma</p>
      <ul id="u1"><li id="l1">1</li><li id="l2">2</li><li id="l3">3</li></ul>
      <a id="a1" href="#">link</a>
      <input id="i1" type="checkbox" checked/>
      <input id="i2" type="text" value="Foo"/>
    </div>
    <h1 id="h1">H</h1>
    </body></html>
    """

    CUSTOM = {
        ':--box': 'div, section',
        ':--special': ':is(.a, .c):not(.b)',
        ':--ref': ':has(:--special)',
        ':--header': 'h1, h2',
    }

    SELECTORS = (
        'div:has(> p:is(.a, .b):not(.c)) > p:nth-of-type(1)',
        'p:lang(en):-soup-contains("alpha")',
        ':-soup-contains-own("alpha")',
        ':--box:has(:--special)',
        ':--ref',
        ':checked',
        'input[type="text"][value="foo" i]',
        'ul > li:nth-child(odd)',
        'p ~ p',
        'a:any-link',
        ':--special, h1',
        'p:focus, div',
        ':scope > p',
    )

    def setUp(self):
        """Setup."""

        super().setUp()
        self.soup = self.soup(self.MARKUP, 'html.parser')

    def _round_trip(self, selector: sv.SoupSieve) -> sv.SoupSieve:
        """Export and re-import a compiled selector."""

        document = selector.to_json()
        # The document must be plain JSON built only from JSON-native values.
        decoded = json.loads(document)
        self.assertEqual(decoded['version'], cg.GRAPH_VERSION)
        return sv.SoupSieve.from_json(document)

    def test_round_trip_equivalence(self):
        """Nested :is/:not/:has selectors match identically after a round trip."""

        for pattern in self.SELECTORS:
            original = sv.compile(
                pattern,
                {'html': 'http://www.w3.org/1999/xhtml'},
                custom=self.CUSTOM
            )
            loaded = self._round_trip(original)
            self.assertEqual(loaded, original)
            self.assertIsNot(loaded, original)

            expected = [el.attrs.get('id') for el in original.select(self.soup)]
            self.assertEqual([el.attrs.get('id') for el in loaded.select(self.soup)], expected)
            self.assertEqual(
                [el.attrs.get('id') for el in loaded.filter(self.soup.find_all(True))],
                [el.attrs.get('id') for el in original.filter(self.soup.find_all(True))]
            )
            for element in self.soup.find_all(True):
                self.assertEqual(loaded.match(element), original.match(element))
                closest_original = original.closest(element)
                closest_loaded = loaded.closest(element)
                self.assertEqual(
                    None if closest_original is None else closest_original.attrs.get('id'),
                    None if closest_loaded is None else closest_loaded.attrs.get('id')
                )

    def test_all_node_types_round_trip(self):
        """A selector exercising every node type survives the round trip unchanged."""

        original = sv.compile(
            'p.class#id[data-x="v"][type="submit"]:nth-child(2n+1 of .a):lang(en, en-GB)'
            ':-soup-contains("text", "other"):has(> span:is(.a, .b):not(.c))',
            {'html': 'http://www.w3.org/TR/html4/'},
            custom=self.CUSTOM
        )
        loaded = self._round_trip(original)
        self.assertEqual(loaded, original)
        types = {node['type'] for node in json.loads(original.to_json())['nodes']}
        self.assertEqual(
            types,
            {
                'Selector', 'SelectorTag', 'SelectorAttribute', 'SelectorContains', 'SelectorNth',
                'SelectorLang', 'SelectorList'
            }
        )
        # The case-insensitive HTML attribute keeps both regex patterns and the flag.
        attribute = loaded.selectors[0].attributes[1]
        original_attribute = original.selectors[0].attributes[1]
        self.assertTrue(attribute.ignore_case)
        self.assertIsNotNone(attribute.pattern)
        self.assertIsNotNone(attribute.xml_type_pattern)
        self.assertEqual(attribute, original_attribute)

    def test_shared_substructure_is_preserved(self):
        """An object shared inside the graph stays shared after import."""

        original = sv.compile(':checked:checked')
        first, second = original.selectors[0].selectors
        self.assertIs(first, second)

        loaded = self._round_trip(original)
        loaded_first, loaded_second = loaded.selectors[0].selectors
        self.assertIs(loaded_first, loaded_second)
        self.assertIsNot(loaded_first, first)
        self.assertEqual(loaded, original)

        # A shared object is stored once, so the node table does not duplicate it.
        document = json.loads(original.to_json())
        single = json.loads(sv.compile(':checked').to_json())
        self.assertEqual(len(document['nodes']), len(single['nodes']))

    def test_custom_aliases_are_exported_expanded(self):
        """Custom aliases are stored as compiled lists and remain shared with the root."""

        original = sv.compile(':--header:nth-child(1)', custom=self.CUSTOM)
        document = json.loads(original.to_json())
        self.assertIn('custom', document)
        self.assertEqual(set(document['custom']), {':--box', ':--special', ':--ref', ':--header'})

        loaded = sv.SoupSieve.from_json(json.dumps(document))
        self.assertIsInstance(loaded.custom, ct.CustomSelectors)
        self.assertEqual(loaded, original)
        self.assertEqual(
            [el.attrs['id'] for el in loaded.select(self.soup)],
            [el.attrs['id'] for el in original.select(self.soup)]
        )
        # The expanded alias list referenced by the root is the same object as the map value.
        alias = loaded.custom[':--header']
        referenced = loaded.selectors[0].selectors[0]
        self.assertIs(alias, referenced)

    def test_namespaces_flags_and_null_are_preserved(self):
        """Namespaces, match flags and the null selector survive the round trip."""

        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        original = sv.compile('svg|a', namespaces, flags=sv.NOCACHE)
        loaded = self._round_trip(original)
        self.assertEqual(loaded, original)
        self.assertIsInstance(loaded.namespaces, ct.Namespaces)
        self.assertEqual(dict(loaded.namespaces), namespaces)
        self.assertEqual(loaded.flags, sv.NOCACHE)

        null_case = sv.compile('p:focus, div')
        null_loaded = self._round_trip(null_case)
        self.assertIs(null_loaded.selectors[0], ct.Null)
        self.assertIsInstance(null_loaded.selectors[1], ct.Selector)

    def test_import_does_not_recompile_css(self):
        """Loading uses the stored graph and never the parser or the diagnostic pattern."""

        original = sv.compile('div:has(> span.a), :--header', custom=self.CUSTOM)
        document = json.loads(original.to_json())

        def fail(*args, **kwargs):
            raise AssertionError('the CSS parser must not run while importing a graph')

        parser = cp.CSSParser
        cached = cp._cached_css_compile
        cp.CSSParser = fail
        cp._cached_css_compile = fail
        try:
            loaded = sv.SoupSieve.from_json(json.dumps(document))
            # Tamper with the diagnostic string; matching must still follow the compiled graph.
            document['pattern'] = '((('
            tampered = sv.SoupSieve.from_json(json.dumps(document))
        finally:
            cp.CSSParser = parser
            cp._cached_css_compile = cached

        self.assertEqual(loaded, original)
        self.assertEqual(
            [el.attrs['id'] for el in tampered.select(self.soup)],
            [el.attrs['id'] for el in original.select(self.soup)]
        )

    def test_imported_graph_is_immutable(self):
        """Imported selector objects cannot be mutated."""

        loaded = self._round_trip(sv.compile('div:has(> span.a)', custom=self.CUSTOM))
        with self.assertRaises(AttributeError):
            loaded.flags = 1
        with self.assertRaises(AttributeError):
            loaded.selectors[0].flags = 1
        with self.assertRaises(TypeError):
            loaded.custom[':--new'] = loaded.selectors
        with self.assertRaises(TypeError):
            loaded.namespaces['x'] = 'y'

        # A deep copy of an imported graph stays equal and usable.
        duplicated = copy.deepcopy(loaded)
        self.assertEqual(duplicated, loaded)
        self.assertEqual(
            [el.attrs['id'] for el in duplicated.select(self.soup)],
            [el.attrs['id'] for el in loaded.select(self.soup)]
        )

    def test_rejects_tampered_references_and_types(self):
        """Corrupt references, cycles and node types fail before any DOM traversal."""

        document = json.loads(sv.compile('div:has(> span:is(.a, .b):not(.c))').to_json())
        list_index = next(
            index for index, node in enumerate(document['nodes'])
            if node['type'] == 'SelectorList' and node['fields'][0]
        )
        selector_index = next(
            index for index, node in enumerate(document['nodes']) if node['type'] == 'Selector'
        )

        def expect_error(mutate):
            tampered = copy.deepcopy(document)
            mutate(tampered)
            with self.assertRaises(cg.GraphFormatError):
                # No soup/DOM object is supplied; validation must fail on the document alone.
                sv.SoupSieve.from_json(json.dumps(tampered))

        expect_error(lambda data: data['nodes'][list_index]['fields'][0].__setitem__(0, 99999))
        expect_error(lambda data: data['nodes'][list_index]['fields'][0].__setitem__(0, list_index))
        expect_error(lambda data: data['nodes'][list_index]['fields'][0].__setitem__(0, 0))
        expect_error(
            lambda data: data['nodes'][selector_index]['fields'].__setitem__(6, selector_index)
        )
        expect_error(
            lambda data: data['nodes'][selector_index]['fields'].__setitem__(6, None)
        )
        expect_error(lambda data: data['nodes'][0].__setitem__('type', 'os.system'))
        expect_error(
            lambda data: data['nodes'][0].__setitem__(
                'fields', data['nodes'][0]['fields'] + [1]
            )
        )
        expect_error(lambda data: data['nodes'][0]['fields'].__setitem__(1, 1))

    def test_rejects_malformed_documents(self):
        """Unknown versions, bad fields and invalid regex are rejected up front."""

        document = json.loads(sv.compile('[type="submit"]').to_json())

        def expect_error(mutate):
            tampered = copy.deepcopy(document)
            mutate(tampered)
            with self.assertRaises(cg.GraphFormatError):
                sv.SoupSieve.from_json(json.dumps(tampered))

        expect_error(lambda data: data.__setitem__('version', cg.GRAPH_VERSION + 1))
        expect_error(lambda data: data.__setitem__('version', str(cg.GRAPH_VERSION)))
        expect_error(lambda data: data.__setitem__('evil', 1))
        expect_error(lambda data: data.pop('root'))
        expect_error(lambda data: data.__setitem__('nodes', []))
        expect_error(lambda data: data.__setitem__('flags', '1'))
        expect_error(lambda data: data.__setitem__('flags', -1))
        expect_error(lambda data: data.__setitem__('root', '0'))
        attribute_index = next(
            index for index, node in enumerate(document['nodes']) if node['type'] == 'SelectorAttribute'
        )
        expect_error(lambda data: data['nodes'][attribute_index]['fields'].__setitem__(2, '['))

        with self.assertRaises(cg.GraphFormatError):
            sv.SoupSieve.from_json('{not valid json')
        with self.assertRaises(cg.GraphFormatError):
            sv.SoupSieve.from_json(123)  # type: ignore[arg-type]

    def test_rejects_bad_custom_and_namespace_maps(self):
        """Invalid custom alias names and namespace value types are rejected."""

        document = json.loads(sv.compile('a', custom=self.CUSTOM).to_json())

        def expect_error(mutate):
            tampered = copy.deepcopy(document)
            mutate(tampered)
            with self.assertRaises(cg.GraphFormatError):
                sv.SoupSieve.from_json(json.dumps(tampered))

        key = next(iter(document['custom']))
        expect_error(lambda data: data['custom'].__setitem__(':--bad name!', data['custom'].pop(key)))

        def duplicate_alias(data):
            ref = next(iter(data['custom'].values()))
            data['custom'] = {':--x': ref, r':\--x': ref}

        expect_error(duplicate_alias)
        expect_error(lambda data: data['custom'].__setitem__(key, 99999))
        expect_error(lambda data: data.__setitem__('namespaces', {'x': 1}))
        expect_error(lambda data: data.__setitem__('namespaces', 'not-a-map'))

    def test_node_limit_is_enforced(self):
        """Documents above the node limit are rejected before construction."""

        document = json.loads(sv.compile('div').to_json())
        original_limit = cg.GRAPH_NODE_LIMIT
        cg.GRAPH_NODE_LIMIT = len(document['nodes']) - 1
        try:
            with self.assertRaises(cg.GraphFormatError):
                sv.SoupSieve.from_json(json.dumps(document))
        finally:
            cg.GRAPH_NODE_LIMIT = original_limit

    def test_indented_json_is_plain_data(self):
        """Indented export stays JSON-native and round trips."""

        original = sv.compile('div > span', custom=self.CUSTOM)
        document = original.to_json(indent=2)
        self.assertIn('\n', document)
        loaded = sv.SoupSieve.from_json(document)
        self.assertEqual(loaded, original)
