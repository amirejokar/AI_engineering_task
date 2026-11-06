from li_crawler.adapters.outbound.parsing.listing import parse_company_people, parse_company_search


def test_company_search_picks_result_cards(load_fixture):
    companies = parse_company_search(load_fixture("company_search.html"))

    assert [c.slug for c in companies] == ["acme", "acme-international"]
    acme = companies[0]
    assert acme.name == "Acme Corp"
    assert acme.industry == "Software Development"
    assert acme.location == "Tehran, Tehran"
    assert acme.url == "https://www.linkedin.com/company/acme/"


def test_company_people_deduplicates_and_ignores_header(load_fixture):
    people = parse_company_people(load_fixture("company_people.html"))

    assert [p.slug for p in people] == ["sara", "reza-test-123"]
    assert (people[0].name, people[0].headline) == ("Sara Example", "Senior Engineer")
    assert people[1].headline == "Human Resources Manager"
    assert people[1].url == "https://www.linkedin.com/in/reza-test-123/"
