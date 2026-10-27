"""CLI entry point for the resilient scraper demo.

Reads one or more product listing pages (over HTTP via :mod:`scraper.fetch`, or
from a local fixture directory with ``--fixtures``), parses them, de-duplicates
records by URL, writes ``output/products.csv`` and writes a small run report
JSON with counts, errors and duration.

The process exits non-zero on any failure so that cron or a monitoring system
notices instead of a quiet broken run.
"""

import argparse
import csv
import json
import os
import sys
import time

from scraper.fetch import FetchError, fetch
from scraper.parse import ParseError, parse_listing

DEFAULT_OUTPUT_DIR = "output"
CSV_FIELDS = ("name", "price", "url")


def _iter_sources(args):
    """Yield ``(label, html)`` pairs from fixtures or live URLs.

    Raises on the first unreadable source so the caller records it as an error.
    """
    if args.fixtures:
        names = sorted(
            name
            for name in os.listdir(args.fixtures)
            if name.endswith(".html")
        )
        if not names:
            raise FileNotFoundError(
                "no .html fixtures found in {}".format(args.fixtures)
            )
        for name in names:
            path = os.path.join(args.fixtures, name)
            with open(path, "r", encoding="utf-8") as handle:
                yield path, handle.read()
    else:
        for url in args.urls:
            yield url, fetch(url, polite_delay=args.polite_delay)


def dedupe_by_url(products):
    """Return records with duplicate URLs removed, keeping first seen order."""
    seen = set()
    unique = []
    for product in products:
        if product.url in seen:
            continue
        seen.add(product.url)
        unique.append(product)
    return unique


def write_csv(products, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for product in products:
            writer.writerow(product.as_dict())


def write_report(report, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def run(args, clock=time.monotonic):
    """Run the scrape and return ``(report, exit_code)``.

    ``clock`` is injectable so tests can measure duration deterministically.
    """
    started = clock()
    errors = []
    all_products = []
    pages_ok = 0
    pages_failed = 0

    try:
        sources = list(_iter_sources(args))
    except (OSError, FetchError) as error:
        sources = []
        errors.append(str(error))

    for label, html in sources:
        try:
            records = parse_listing(html, source=label)
        except ParseError as error:
            pages_failed += 1
            errors.append(str(error))
            continue
        pages_ok += 1
        all_products.extend(records)

    unique = dedupe_by_url(all_products)
    duplicates_removed = len(all_products) - len(unique)

    csv_path = os.path.join(args.output_dir, "products.csv")
    report_path = os.path.join(args.output_dir, "run_report.json")

    # Zero results overall is a failure, not a quiet success.
    failed = bool(errors) or not unique
    if not unique and not errors:
        errors.append("zero products collected across all sources")

    if unique:
        write_csv(unique, csv_path)

    report = {
        "ok": not failed,
        "pages_ok": pages_ok,
        "pages_failed": pages_failed,
        "products_written": len(unique),
        "duplicates_removed": duplicates_removed,
        "errors": errors,
        "duration_seconds": round(clock() - started, 6),
        "output_csv": csv_path if unique else None,
    }
    write_report(report, report_path)

    return report, (1 if failed else 0)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Resilient scraper demo (fixtures or live URLs)."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="One or more listing URLs to fetch (ignored with --fixtures).",
    )
    parser.add_argument(
        "--fixtures",
        metavar="DIR",
        help="Read *.html from this directory instead of the network.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Where to write products.csv and run_report.json.",
    )
    parser.add_argument(
        "--polite-delay",
        type=float,
        default=1.0,
        help="Seconds to wait before each live request.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.fixtures and not args.urls:
        parser.error("provide URLs to fetch or use --fixtures DIR")

    report, exit_code = run(args)

    summary = "{}: {} product(s), {} page(s) ok, {} failed, {} dup(s) removed".format(
        "OK" if report["ok"] else "FAILED",
        report["products_written"],
        report["pages_ok"],
        report["pages_failed"],
        report["duplicates_removed"],
    )
    stream = sys.stdout if report["ok"] else sys.stderr
    print(summary, file=stream)
    for error in report["errors"]:
        print("  error: {}".format(error), file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
