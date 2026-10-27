# resilient-scraper-demo

A small portfolio sample of a web scraper that is built to fail loudly rather
than break quietly. The point of the project is the reliability engineering
around the scrape, not the scraping of any particular site.

## What it is

A scraper has three jobs here:

1. **Fetch** pages over HTTP with timeouts, retries, exponential backoff with
   jitter, a polite delay between requests and a custom User-Agent. The HTTP
   layer is injectable, so the logic can be tested without the network.
2. **Parse** a product listing into records of name, price and URL. If the
   expected structure is missing it raises a clear error, so a layout change on
   the source site is caught rather than ignored. Zero results is treated as a
   failure, not a success.
3. **Run** the whole thing from the command line: read pages, de-duplicate by
   URL, write `output/products.csv`, write a small JSON run report with counts,
   errors and duration, and exit with a non-zero status on failure so that cron
   or a monitor notices.

## Layout

```
scraper/fetch.py   fetch with retries, backoff, jitter, polite delay
scraper/parse.py   parse listing HTML into records, detect layout changes
scraper/run.py     CLI: fetch or fixtures, dedupe, CSV, run report, exit code
tests/             unittest suite and HTML fixtures
```

## Requirements

Python 3 only. The parser uses the standard library `html.parser`, so there are
no third party dependencies to install. `beautifulsoup4` is not required.

## How to run the tests

```
python3 -m unittest
```

All HTTP is faked in the tests, so nothing touches the network.

## How to run on fixtures

Run against the bundled good page (succeeds, writes a CSV, exits 0):

```
python3 -m scraper.run --fixtures tests/fixtures_good
```

Run against all the fixtures, including a changed layout and an empty page
(demonstrates failure detection, exits 1):

```
python3 -m scraper.run --fixtures tests/fixtures
```

Output is written under `output/`:

- `output/products.csv` the de-duplicated records
- `output/run_report.json` counts, errors and duration

You can also point it at live URLs instead of fixtures, for example
`python3 -m scraper.run https://example.invalid/listing`, but see the note
below.

## Reliability notes

- **Retries with backoff and jitter.** Transient network errors are retried a
  few times. The wait grows exponentially and is capped, with a little random
  jitter added so that many workers do not retry in lockstep.
- **Polite by default.** A delay is applied before each live request so the
  scraper does not hammer a server.
- **Injectable HTTP.** `fetch` takes the HTTP function, the sleep function and
  the random source as arguments. Tests pass fakes, so retry and backoff
  behaviour is verified deterministically and offline.
- **Layout-change detection.** The parser knows the shape it expects. If the
  product containers are gone, or a record is missing its name, price or URL,
  it raises a clear `ParseError` naming the problem.
- **Zero results is a failure.** An empty result set almost always means the
  page changed or the request was blocked, so it is reported as a failure
  rather than written out as an empty success.
- **Visible failure.** The run writes a JSON report and exits non-zero on any
  failure, so a scheduled run that breaks is noticed instead of silently
  producing an empty file.

## Honest note

This is a demonstration. It ships with local HTML fixtures and dummy data only.
It has not been pointed at any live website, and the example URLs use the
reserved `example.invalid` domain. If you did adapt it for a real site, you
would need to check that site's terms of use and `robots.txt` first.
