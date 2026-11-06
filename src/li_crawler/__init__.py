"""LinkedIn organisation crawler (hexagonal architecture).

domain/        entities and errors - no dependencies
application/   use cases + ports (interfaces)
adapters/      inbound (CLI) and outbound (Playwright, BeautifulSoup, storage, queue)
container.py   composition root
"""

__version__ = "0.1.0"
