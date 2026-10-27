"""Tests for parsing, layout-change detection and zero-results handling."""

import os
import unittest

from scraper.parse import ParseError, parse_listing

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def read_fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read()


class ParseListingTests(unittest.TestCase):
    def test_good_page_parses_records(self):
        records = parse_listing(read_fixture("good.html"), source="good.html")
        # Four product blocks, including one duplicate URL (dedupe is run().)
        self.assertEqual(len(records), 4)
        first = records[0]
        self.assertEqual(first.name, "Blue Widget")
        self.assertEqual(first.price, "12.99")
        self.assertEqual(
            first.url, "https://example.invalid/products/blue-widget"
        )

    def test_changed_layout_raises_parse_error(self):
        with self.assertRaises(ParseError) as ctx:
            parse_listing(
                read_fixture("changed_layout.html"),
                source="changed_layout.html",
            )
        self.assertIn("no product containers", str(ctx.exception))

    def test_empty_page_raises_parse_error(self):
        with self.assertRaises(ParseError):
            parse_listing(read_fixture("empty.html"), source="empty.html")

    def test_missing_field_raises_parse_error(self):
        html = (
            '<div class="product">'
            '<h2 class="name">No Price Widget</h2>'
            '<a class="link" href="https://example.invalid/x">x</a>'
            "</div>"
        )
        with self.assertRaises(ParseError) as ctx:
            parse_listing(html)
        self.assertIn("price", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
