"""Command-line interface (driving adapter).

python -m li_crawler login
python -m li_crawler crawl "Cafe Bazaar" --max-profiles 10
python -m li_crawler crawl https://www.linkedin.com/company/cafebazaar/
python -m li_crawler reparse
"""

from __future__ import annotations

import argparse
import logging
import sys

from li_crawler import container
from li_crawler.adapters.outbound.playwright_gateway import PlaywrightLinkedInGateway
from li_crawler.application import ALL_SECTIONS, CrawlReport, CrawlRequest
from li_crawler.config import Settings
from li_crawler.domain import CrawlerError, ProfileSection

logger = logging.getLogger("li_crawler")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    settings = Settings.from_env().with_overrides(
        headless=args.headless or None,
        cdp_url=getattr(args, "cdp_url", None),
        queue_backend=getattr(args, "queue", None),
    )
    try:
        return args.handler(args, settings)
    except CrawlerError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted.")
        return 130


# -- commands ----------------------------------------------------------------


def _login(_: argparse.Namespace, settings: Settings) -> int:
    with PlaywrightLinkedInGateway(settings.browser, _prompt_for_login) as gateway:
        gateway.ensure_session()
        logger.info("Logged in. The session is stored in %s", settings.browser.user_data_dir)
    return 0


def _crawl(args: argparse.Namespace, settings: Settings) -> int:
    request = CrawlRequest(
        company=args.company,
        max_profiles=args.max_profiles,
        sections=tuple(ProfileSection(s) for s in args.sections) if args.sections else ALL_SECTIONS,
    )
    with PlaywrightLinkedInGateway(settings.browser, _prompt_for_login) as gateway:
        report = container.build_crawl_use_case(settings, gateway).execute(request)
    _print_report(report, settings)
    return 0 if report.saved and not report.aborted_reason else 1


def _reparse(_: argparse.Namespace, settings: Settings) -> int:
    slugs = container.build_reparse_use_case(settings).execute()
    print(f"Re-parsed {len(slugs)} profiles from {settings.raw_dir}")
    return 0


# -- wiring ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="li_crawler", description="LinkedIn organisation crawler")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--headless", action="store_true", help="hide the browser window")
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login", help="open the browser and log in once by hand")
    login.set_defaults(handler=_login)

    crawl = commands.add_parser("crawl", help="crawl the employees of a company")
    crawl.add_argument("company", help='company name (e.g. "Cafe Bazaar") or LinkedIn company URL')
    crawl.add_argument("-n", "--max-profiles", type=int, default=10)
    crawl.add_argument(
        "--sections",
        nargs="+",
        choices=[s.value for s in ProfileSection],
        help="profile sections to collect (default: all)",
    )
    crawl.add_argument("--queue", choices=["memory", "redis"], help="task queue backend")
    crawl.add_argument("--cdp-url", help="attach to a running Chrome, e.g. http://localhost:9222")
    crawl.set_defaults(handler=_crawl)

    reparse = commands.add_parser("reparse", help="rebuild the dataset from saved HTML (offline)")
    reparse.set_defaults(handler=_reparse)
    return parser


def _prompt_for_login() -> None:
    print(
        "\n>>> Log in to LinkedIn in the opened browser window"
        " (complete any verification yourself). Waiting for the feed to appear...",
        flush=True,
    )


def _print_report(report: CrawlReport, settings: Settings) -> None:
    company = report.company.name if report.company else "-"
    print(f"\nCompany:    {company}")
    print(f"Discovered: {report.discovered}")
    print(f"Saved:      {len(report.saved)}")
    if report.failed:
        print("Failed:     " + ", ".join(f"{slug} ({err})" for slug, err in report.failed.items()))
    if report.aborted_reason:
        print(f"Aborted:    {report.aborted_reason}")
    print(f"Output:     {settings.data_dir.resolve()}")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
