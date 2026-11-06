class CrawlerError(Exception):
    """Base class for all expected crawler failures."""


class AuthenticationRequiredError(CrawlerError):
    """The session is logged out or LinkedIn raised a security checkpoint.

    The crawler never tries to get around this: it stops and asks a human.
    """


class CompanyNotFoundError(CrawlerError):
    """No company matched the user's query."""


class PageLoadError(CrawlerError):
    """A page failed to load (timeout, network error). Safe to retry."""
