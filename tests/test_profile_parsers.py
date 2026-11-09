from li_crawler.adapters.outbound.parsing.activity import parse_activity_page
from li_crawler.adapters.outbound.parsing.education import parse_education_page
from li_crawler.adapters.outbound.parsing.experience import parse_experience_page
from li_crawler.adapters.outbound.parsing.skills import parse_skills_page
from li_crawler.adapters.outbound.parsing.top_card import parse_top_card
from li_crawler.domain import ActivityKind


def test_experience_grouped_and_single_roles(load_fixture):
    roles = parse_experience_page(load_fixture("experience.html"))

    assert [r.title for r in roles] == [
        "Engineering Lead",
        "Senior Engineer",
        "Freelance Developer",
        "Intern",
    ]
    lead, senior, freelance, intern = roles

    assert lead.company == senior.company == "Acme Corp"
    assert lead.company_url == "https://www.linkedin.com/company/acme/"
    assert lead.date_range.is_current and lead.description is None

    assert senior.employment_type == "Full-time"
    assert (senior.location, senior.workplace_type) == ("Tehran Province, Iran", "Hybrid")
    assert senior.description == "Built the payments platform.\nLed a team of 5."
    assert senior.skills == ["Android", "Kotlin"]

    assert (freelance.company, freelance.employment_type) == ("Self Studio", "Freelance")
    assert freelance.date_range.end.year == 2022
    assert freelance.description.startswith("Shipped 35")

    assert (intern.company, intern.employment_type) == ("Small Shop", "Internship")
    assert intern.company_url is None
    assert intern.workplace_type == "Remote"


def test_education(load_fixture):
    first, second = parse_education_page(load_fixture("education.html"))

    assert first.school == "Amirkabir University of Technology"
    assert first.school_url == "https://www.linkedin.com/school/15095155/"
    assert (first.degree, first.field_of_study) == (
        "Bachelor of Science - BS",
        "Computer Engineering",
    )
    assert first.date_range.start.year == 2021 and first.date_range.end.year == 2025
    assert (first.grade, first.activities) == ("18.5", "ACM Club")

    assert second.school == "Some High School"
    assert (second.degree, second.field_of_study) == (None, "Mathematics")


def test_empty_section_placeholder_is_ignored():
    html = (
        "<html><main><section><div><p>Education</p></div>"
        "<div><p>Education that Sara adds will appear here.</p></div>"
        "</section></main></html>"
    )
    assert parse_education_page(html) == []


def test_lazy_loaded_batches_are_all_collected():
    # each batch loaded by scrolling sits in its own container
    def batch(*names):
        entries = "<div><hr></div>".join(
            f"<div><p>{n}</p><p>1 endorsement</p></div>" for n in names
        )
        return f"<div>{entries}</div>"

    html = (
        "<html><main><section><div><p>Skills</p></div><div>"
        + batch("Python", "SQL")
        + batch("Kafka", "Redis")
        + "</div></section></main></html>"
    )
    assert [s.name for s in parse_skills_page(html)] == ["Python", "SQL", "Kafka", "Redis"]


def test_skills(load_fixture):
    kotlin, android, leadership = parse_skills_page(load_fixture("skills.html"))

    assert (kotlin.name, kotlin.endorsements) == ("Kotlin", 5)
    assert kotlin.contexts == ["Senior Engineer at Acme Corp"]
    assert android.assessment_passed and android.endorsements == 4
    assert leadership.endorsements is None and leadership.contexts == []


def test_top_card(load_fixture):
    card = parse_top_card(load_fixture("main.html"))

    assert card.name == "Sara Example"
    assert card.headline == "Senior Engineer at Acme Corp"
    assert card.location == "Tehran Province, Iran"
    assert card.connections == 500
    assert card.followers == 2115
    assert card.about == "I build mobile apps.\nKotlin fan."


def test_activity(load_fixture):
    repost, post = parse_activity_page(load_fixture("activity.html"))

    assert repost.kind is ActivityKind.REPOST
    assert (repost.actor, repost.author, repost.posted_ago) == ("Sara Example", "Acme Corp", "3w")
    assert repost.text == "We are hiring Android engineers! #hiring Join us.\nApply today."
    assert (repost.reactions, repost.comments, repost.reposts) == (376, 11, 9)

    assert post.kind is ActivityKind.POST
    assert post.author == "Sara Example"
    assert post.posted_ago == "6mo" and post.edited
    assert "hexagonal" in post.text
    assert (post.reactions, post.comments, post.reposts) == (1204, 0, 7)


def test_activity_limit(load_fixture):
    assert len(parse_activity_page(load_fixture("activity.html"), limit=1)) == 1
