"""Parse a product listing page into records.

The parser expects a specific structure. If that structure is missing it raises
:class:`ParseError` rather than silently returning nothing, so a layout change on
the source site is caught loudly. An empty result set is also treated as a
failure, because "zero products" almost always means the page changed or the
request was blocked, not that the shop is genuinely empty.

A product is expected to look like::

    <div class="product">
        <h2 class="name">Widget</h2>
        <span class="price">12.99</span>
        <a class="link" href="/widget">details</a>
    </div>
"""

from html.parser import HTMLParser


class ParseError(Exception):
    """Raised when the page does not match the expected product layout."""


class Product:
    """A single parsed product record."""

    __slots__ = ("name", "price", "url")

    def __init__(self, name, price, url):
        self.name = name
        self.price = price
        self.url = url

    def as_dict(self):
        return {"name": self.name, "price": self.price, "url": self.url}

    def __eq__(self, other):
        if not isinstance(other, Product):
            return NotImplemented
        return self.as_dict() == other.as_dict()

    def __repr__(self):
        return "Product(name={!r}, price={!r}, url={!r})".format(
            self.name, self.price, self.url
        )


class _ListingParser(HTMLParser):
    """Collect product records from the expected listing structure.

    Uses the standard library ``html.parser`` so there are no dependencies.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.products = []
        self._in_product = False
        self._capture = None  # which field we are currently reading text into
        self._name = None
        self._price = None
        self._url = None

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if "product" in classes:
            self._in_product = True
            self._name = None
            self._price = None
            self._url = None
            return
        if not self._in_product:
            return
        if "name" in classes:
            self._capture = "name"
        elif "price" in classes:
            self._capture = "price"
        elif "link" in classes:
            self._url = dict(attrs).get("href")

    def handle_data(self, data):
        if not self._in_product or self._capture is None:
            return
        text = data.strip()
        if not text:
            return
        if self._capture == "name":
            self._name = text
        elif self._capture == "price":
            self._price = text

    def handle_endtag(self, tag):
        if self._capture is not None and tag in ("h2", "span"):
            self._capture = None
        if tag == "div" and self._in_product:
            # Only record a product once we leave its container.
            self.products.append((self._name, self._price, self._url))
            self._in_product = False


def parse_listing(html, source=""):
    """Parse ``html`` into a list of :class:`Product` records.

    ``source`` is an optional label (file name or URL) used in error messages.

    Raises :class:`ParseError` if the page has no product containers at all
    (a likely layout change), if any product is missing a required field, or if
    the parse yields zero usable records.
    """
    where = " in {}".format(source) if source else ""

    parser = _ListingParser()
    parser.feed(html)
    parser.close()

    if not parser.products:
        raise ParseError(
            "no product containers found{}: the page layout may have changed "
            "or the request was blocked".format(where)
        )

    records = []
    for index, (name, price, url) in enumerate(parser.products):
        missing = [
            field
            for field, value in (("name", name), ("price", price), ("url", url))
            if not value
        ]
        if missing:
            raise ParseError(
                "product #{}{} is missing required field(s): {}".format(
                    index + 1, where, ", ".join(missing)
                )
            )
        records.append(Product(name=name, price=price, url=url))

    # Zero usable records is a failure, not a quiet success.
    if not records:
        raise ParseError(
            "parsed zero products{}: treating as a failure".format(where)
        )

    return records
