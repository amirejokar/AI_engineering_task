from __future__ import annotations

from collections.abc import Callable, Mapping

from li_crawler.adapters.outbound.parsing.activity import parse_activity_page
from li_crawler.adapters.outbound.parsing.dom import main_region, make_soup
from li_crawler.adapters.outbound.parsing.education import parse_education_page
from li_crawler.adapters.outbound.parsing.experience import parse_experience_page
from li_crawler.adapters.outbound.parsing.listing import parse_company_people, parse_company_search
from li_crawler.adapters.outbound.parsing.skills import parse_skills_page
from li_crawler.adapters.outbound.parsing.top_card import TopCard, parse_followers, parse_top_card
from li_crawler.adapters.outbound.urls import profile_url
from li_crawler.domain import Company, EmployeeRef, Profile, ProfileSection


class SoupLinkedInParser:
    def __init__(self, max_activities: int | None = 20) -> None:
        self._max_activities = max_activities

    def parse_company_search(self, html: str) -> list[Company]:
        return parse_company_search(html)

    def parse_company_people(self, html: str) -> list[EmployeeRef]:
        return parse_company_people(html)

    def parse_profile(self, slug: str, pages: Mapping[ProfileSection, str]) -> Profile:
        main_html = pages.get(ProfileSection.MAIN)
        top = parse_top_card(main_html) if main_html else TopCard()
        activity_html = pages.get(ProfileSection.ACTIVITY)

        followers = top.followers
        if followers is None and activity_html:
            followers = parse_followers(main_region(make_soup(activity_html)).get_text(" "))

        return Profile(
            slug=slug,
            url=profile_url(slug),
            name=top.name,
            headline=top.headline,
            location=top.location,
            connections=top.connections,
            followers=followers,
            about=top.about,
            experiences=_parse_optional(pages, ProfileSection.EXPERIENCE, parse_experience_page),
            education=_parse_optional(pages, ProfileSection.EDUCATION, parse_education_page),
            skills=_parse_optional(pages, ProfileSection.SKILLS, parse_skills_page),
            activities=(
                parse_activity_page(activity_html, self._max_activities) if activity_html else []
            ),
        )


def _parse_optional[T](
    pages: Mapping[ProfileSection, str],
    section: ProfileSection,
    parse: Callable[[str], list[T]],
) -> list[T]:
    html = pages.get(section)
    return parse(html) if html else []
