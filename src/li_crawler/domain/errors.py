class CrawlerError(Exception):
    pass


class AuthenticationRequiredError(CrawlerError):
    # logged out or hit a checkpoint - we stop here, never try to get around it
    pass


class CompanyNotFoundError(CrawlerError):
    pass


class PageLoadError(CrawlerError):
    # timeouts / network errors, safe to retry
    pass
