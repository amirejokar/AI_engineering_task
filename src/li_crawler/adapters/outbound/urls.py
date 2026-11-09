from __future__ import annotations

from urllib.parse import quote

from li_crawler.domain import ProfileSection

BASE_URL = "https://www.linkedin.com"

_SECTION_PATHS = {
    ProfileSection.MAIN: "",
    ProfileSection.EXPERIENCE: "details/experience/",
    ProfileSection.EDUCATION: "details/education/",
    ProfileSection.SKILLS: "details/skills/",
    ProfileSection.ACTIVITY: "recent-activity/all/",
}


def profile_url(slug: str, section: ProfileSection = ProfileSection.MAIN) -> str:
    return f"{BASE_URL}/in/{slug}/{_SECTION_PATHS[section]}"


def company_url(slug: str) -> str:
    return f"{BASE_URL}/company/{slug}/"


def company_people_url(slug: str) -> str:
    return f"{BASE_URL}/company/{slug}/people/"


def company_search_url(query: str) -> str:
    return f"{BASE_URL}/search/results/companies/?keywords={quote(query)}"


FEED_URL = f"{BASE_URL}/feed/"
