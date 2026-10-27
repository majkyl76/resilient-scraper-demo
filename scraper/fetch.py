"""HTTP fetching with retries, backoff, jitter, polite delay and a custom User-Agent.

The HTTP layer is injectable: pass your own ``http_get`` callable so tests never
touch the network. The default transport uses ``urllib`` from the standard
library.
"""

import random
import time
import urllib.error
import urllib.request

DEFAULT_USER_AGENT = "resilient-scraper-demo/1.0 (+https://example.invalid/bot)"


class FetchError(Exception):
    """Raised when a URL cannot be fetched after all retries."""


def urllib_get(url, timeout, user_agent):
    """Default HTTP transport built on the standard library.

    Returns the response body as text. Raises on any HTTP or network error so
    the retry logic in :func:`fetch` can decide whether to try again.
    """
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch(
    url,
    http_get=urllib_get,
    retries=3,
    timeout=10.0,
    backoff_base=0.5,
    backoff_cap=10.0,
    jitter=0.5,
    polite_delay=1.0,
    user_agent=DEFAULT_USER_AGENT,
    sleep=time.sleep,
    rng=random.random,
):
    """Fetch ``url``, retrying transient failures with exponential backoff.

    Parameters
    ----------
    url:
        The URL to fetch.
    http_get:
        Injectable transport callable ``(url, timeout, user_agent) -> text``.
        Defaults to :func:`urllib_get`. Tests pass a fake here.
    retries:
        Number of attempts before giving up (must be at least 1).
    timeout:
        Per request timeout in seconds, passed to ``http_get``.
    backoff_base:
        Base delay for exponential backoff. Attempt ``n`` waits roughly
        ``backoff_base * 2 ** (n - 1)`` seconds, capped at ``backoff_cap``.
    backoff_cap:
        Upper bound on the backoff delay.
    jitter:
        Maximum extra random delay added to each backoff, to avoid thundering
        herds. Set to 0 for deterministic waits.
    polite_delay:
        Delay applied before the first request, so repeated calls stay polite.
    user_agent:
        Custom User-Agent string sent with the request.
    sleep:
        Injectable sleep function (defaults to :func:`time.sleep`).
    rng:
        Injectable random source returning a float in ``[0, 1)`` (defaults to
        :func:`random.random`).

    Returns the response body text. Raises :class:`FetchError` if every attempt
    fails.
    """
    if retries < 1:
        raise ValueError("retries must be at least 1")

    # Be polite: wait before hitting the server at all.
    if polite_delay > 0:
        sleep(polite_delay)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return http_get(url, timeout, user_agent)
        except Exception as error:  # noqa: BLE001 - retry any transport error
            last_error = error
            if attempt == retries:
                break
            delay = min(backoff_base * (2 ** (attempt - 1)), backoff_cap)
            if jitter > 0:
                delay += rng() * jitter
            sleep(delay)

    raise FetchError(
        "failed to fetch {!r} after {} attempt(s): {}".format(
            url, retries, last_error
        )
    ) from last_error
