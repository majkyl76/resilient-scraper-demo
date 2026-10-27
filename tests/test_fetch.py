"""Tests for the retry/backoff behaviour of scraper.fetch.

All HTTP is faked, so these tests never touch the network.
"""

import unittest

from scraper.fetch import FetchError, fetch


class FakeHttp:
    """A fake ``http_get`` that fails a set number of times, then succeeds."""

    def __init__(self, fail_times, body="ok"):
        self.fail_times = fail_times
        self.body = body
        self.calls = 0

    def __call__(self, url, timeout, user_agent):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("boom #{}".format(self.calls))
        return self.body


class RecordingSleep:
    """Records every sleep duration instead of actually sleeping."""

    def __init__(self):
        self.waits = []

    def __call__(self, seconds):
        self.waits.append(seconds)


class FetchRetryTests(unittest.TestCase):
    def test_succeeds_without_retry(self):
        http = FakeHttp(fail_times=0, body="page")
        sleep = RecordingSleep()
        result = fetch(
            "https://example.invalid/",
            http_get=http,
            retries=3,
            polite_delay=0,
            sleep=sleep,
            rng=lambda: 0.0,
        )
        self.assertEqual(result, "page")
        self.assertEqual(http.calls, 1)
        # No backoff sleeps because the first attempt worked.
        self.assertEqual(sleep.waits, [])

    def test_retries_then_succeeds(self):
        http = FakeHttp(fail_times=2, body="page")
        sleep = RecordingSleep()
        result = fetch(
            "https://example.invalid/",
            http_get=http,
            retries=3,
            backoff_base=0.5,
            jitter=0,
            polite_delay=0,
            sleep=sleep,
            rng=lambda: 0.0,
        )
        self.assertEqual(result, "page")
        self.assertEqual(http.calls, 3)
        # Two failures means two backoff waits, growing exponentially.
        self.assertEqual(sleep.waits, [0.5, 1.0])

    def test_gives_up_after_retries(self):
        http = FakeHttp(fail_times=5)
        sleep = RecordingSleep()
        with self.assertRaises(FetchError):
            fetch(
                "https://example.invalid/",
                http_get=http,
                retries=3,
                jitter=0,
                polite_delay=0,
                sleep=sleep,
                rng=lambda: 0.0,
            )
        # Exactly ``retries`` attempts, and one fewer backoff waits.
        self.assertEqual(http.calls, 3)
        self.assertEqual(len(sleep.waits), 2)

    def test_backoff_is_capped(self):
        http = FakeHttp(fail_times=4, body="page")
        sleep = RecordingSleep()
        fetch(
            "https://example.invalid/",
            http_get=http,
            retries=5,
            backoff_base=1.0,
            backoff_cap=2.0,
            jitter=0,
            polite_delay=0,
            sleep=sleep,
            rng=lambda: 0.0,
        )
        # Raw backoff would be 1, 2, 4, 8; the cap holds it to 2.
        self.assertEqual(sleep.waits, [1.0, 2.0, 2.0, 2.0])

    def test_jitter_adds_bounded_randomness(self):
        http = FakeHttp(fail_times=1, body="page")
        sleep = RecordingSleep()
        fetch(
            "https://example.invalid/",
            http_get=http,
            retries=2,
            backoff_base=1.0,
            jitter=0.5,
            polite_delay=0,
            sleep=sleep,
            rng=lambda: 1.0,  # maximum jitter
        )
        # Backoff 1.0 plus full jitter 0.5.
        self.assertEqual(sleep.waits, [1.5])

    def test_polite_delay_applied_before_request(self):
        http = FakeHttp(fail_times=0, body="page")
        sleep = RecordingSleep()
        fetch(
            "https://example.invalid/",
            http_get=http,
            retries=1,
            polite_delay=1.0,
            sleep=sleep,
            rng=lambda: 0.0,
        )
        self.assertEqual(sleep.waits, [1.0])

    def test_custom_user_agent_is_passed_through(self):
        seen = {}

        def spy(url, timeout, user_agent):
            seen["user_agent"] = user_agent
            seen["timeout"] = timeout
            return "page"

        fetch(
            "https://example.invalid/",
            http_get=spy,
            retries=1,
            timeout=7.0,
            polite_delay=0,
            user_agent="my-agent/9",
        )
        self.assertEqual(seen["user_agent"], "my-agent/9")
        self.assertEqual(seen["timeout"], 7.0)


if __name__ == "__main__":
    unittest.main()
