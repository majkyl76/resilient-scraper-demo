"""Tests for the run step: dedupe, CSV output, reporting and exit codes."""

import csv
import json
import os
import tempfile
import unittest

from scraper import run as run_module


class Args:
    """Minimal stand-in for the parsed argparse namespace."""

    def __init__(self, fixtures, output_dir, urls=None, polite_delay=0.0):
        self.fixtures = fixtures
        self.output_dir = output_dir
        self.urls = urls or []
        self.polite_delay = polite_delay


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class FakeClock:
    """Returns pre-set times so duration is deterministic."""

    def __init__(self, times):
        self._times = list(times)

    def __call__(self):
        return self._times.pop(0)


class DedupeTests(unittest.TestCase):
    def test_dedupe_by_url_keeps_first_seen(self):
        from scraper.parse import Product

        products = [
            Product("A", "1", "https://example.invalid/a"),
            Product("B", "2", "https://example.invalid/b"),
            Product("A again", "1", "https://example.invalid/a"),
        ]
        unique = run_module.dedupe_by_url(products)
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0].name, "A")
        self.assertEqual(unique[1].name, "B")


class RunFixtureTests(unittest.TestCase):
    def _single_fixture_dir(self, tmp, name):
        """Copy one fixture into an isolated dir so only it is read."""
        src = os.path.join(FIXTURES, name)
        dst_dir = os.path.join(tmp, "in")
        os.makedirs(dst_dir)
        with open(src, "r", encoding="utf-8") as handle:
            data = handle.read()
        with open(os.path.join(dst_dir, name), "w", encoding="utf-8") as handle:
            handle.write(data)
        return dst_dir

    def test_good_page_writes_deduped_csv_and_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_dir = self._single_fixture_dir(tmp, "good.html")
            out_dir = os.path.join(tmp, "out")
            args = Args(fixtures=in_dir, output_dir=out_dir)
            report, code = run_module.run(args, clock=FakeClock([1.0, 1.25]))

            self.assertEqual(code, 0)
            self.assertTrue(report["ok"])
            # Four blocks, one duplicate URL removed, so three written.
            self.assertEqual(report["products_written"], 3)
            self.assertEqual(report["duplicates_removed"], 1)
            self.assertEqual(report["duration_seconds"], 0.25)

            csv_path = os.path.join(out_dir, "products.csv")
            with open(csv_path, encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 3)
            self.assertEqual(
                [row["url"] for row in rows],
                [
                    "https://example.invalid/products/blue-widget",
                    "https://example.invalid/products/red-widget",
                    "https://example.invalid/products/green-widget",
                ],
            )

            report_path = os.path.join(out_dir, "run_report.json")
            with open(report_path, encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertTrue(saved["ok"])

    def test_changed_layout_fails_with_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_dir = self._single_fixture_dir(tmp, "changed_layout.html")
            out_dir = os.path.join(tmp, "out")
            args = Args(fixtures=in_dir, output_dir=out_dir)
            report, code = run_module.run(args, clock=FakeClock([0.0, 0.1]))

            self.assertEqual(code, 1)
            self.assertFalse(report["ok"])
            self.assertEqual(report["pages_failed"], 1)
            self.assertEqual(report["products_written"], 0)
            self.assertTrue(report["errors"])
            # No CSV is written when there is nothing to write.
            self.assertFalse(
                os.path.exists(os.path.join(out_dir, "products.csv"))
            )

    def test_empty_page_is_treated_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_dir = self._single_fixture_dir(tmp, "empty.html")
            out_dir = os.path.join(tmp, "out")
            args = Args(fixtures=in_dir, output_dir=out_dir)
            report, code = run_module.run(args, clock=FakeClock([0.0, 0.1]))

            self.assertEqual(code, 1)
            self.assertFalse(report["ok"])
            self.assertEqual(report["products_written"], 0)

    def test_missing_fixture_dir_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "out")
            args = Args(
                fixtures=os.path.join(tmp, "does-not-exist"),
                output_dir=out_dir,
            )
            report, code = run_module.run(args, clock=FakeClock([0.0, 0.1]))
            self.assertEqual(code, 1)
            self.assertTrue(report["errors"])


class RunLiveFetchTests(unittest.TestCase):
    def test_urls_are_fetched_via_injected_transport(self):
        # Prove run() wires fetch in without touching the network by monkey
        # patching the fetch symbol the run module imported.
        good = os.path.join(FIXTURES, "good.html")
        with open(good, encoding="utf-8") as handle:
            html = handle.read()

        original = run_module.fetch
        try:
            run_module.fetch = lambda url, polite_delay=0.0: html
            with tempfile.TemporaryDirectory() as tmp:
                out_dir = os.path.join(tmp, "out")
                args = Args(
                    fixtures=None,
                    output_dir=out_dir,
                    urls=["https://example.invalid/listing"],
                )
                report, code = run_module.run(args, clock=FakeClock([0.0, 0.5]))
                self.assertEqual(code, 0)
                self.assertEqual(report["products_written"], 3)
        finally:
            run_module.fetch = original


if __name__ == "__main__":
    unittest.main()
