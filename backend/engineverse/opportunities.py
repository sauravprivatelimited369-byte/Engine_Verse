"""Curated, recurring opportunities for students: hackathons, contests,
open-source programmes, scholarships and internships.

Editorial rules (see docs/CONTENT.md):

* Only long-running programmes with an official website are listed. Each
  entry links to the organiser's own page, never to a third-party mirror.
* No dates, deadlines, prize amounts or stipends are stated here: they change
  every cycle and a stale date is worse than none. The page tells learners to
  confirm everything on the official site.
* EngineVerse has no partnership with, and is not endorsed by, any organiser
  listed. Listing is informational only.
* ``last_reviewed`` records when a maintainer last checked the links by hand;
  ``scripts/check_links.py`` re-checks them weekly in CI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

LAST_REVIEWED = "2026-10-23"

CATEGORIES: dict[str, str] = {
    "hackathon": "Hackathons",
    "contest": "Programming contests",
    "open-source": "Open-source programmes",
    "scholarship": "Scholarships and fellowships",
    "internship": "Internships and student benefits",
}

AUDIENCES: dict[str, str] = {
    "school": "School students",
    "college": "College students",
    "everyone": "Open to most learners",
}

REGIONS: dict[str, str] = {
    "india": "India",
    "global": "Global",
}


@dataclass(frozen=True)
class Opportunity:
    slug: str
    title: str
    organiser: str
    category: str
    region: str
    audience: str
    url: str
    summary: str
    cadence: str
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        data = asdict(self)
        data["tags"] = list(self.tags)
        data["category_label"] = CATEGORIES[self.category]
        data["region_label"] = REGIONS[self.region]
        data["audience_label"] = AUDIENCES[self.audience]
        return data


OPPORTUNITIES: tuple[Opportunity, ...] = (
    # --- Hackathons ---------------------------------------------------------
    Opportunity(
        "smart-india-hackathon", "Smart India Hackathon", "Ministry of Education's Innovation Cell and AICTE",
        "hackathon", "india", "college", "https://sih.gov.in/",
        "A nationwide hackathon where student teams from Indian higher-education institutions solve "
        "problem statements published by ministries, departments and industry.",
        "Usually annual; problem statements are published before the internal college round.",
        ("team", "government", "problem statements"),
    ),
    Opportunity(
        "mlh-events", "Major League Hacking events", "Major League Hacking (MLH)",
        "hackathon", "global", "college", "https://www.mlh.com/events",
        "A season calendar of student hackathons, in person and online, run by member events around the world.",
        "Events run throughout the year.",
        ("team", "online", "beginner-friendly"),
    ),
    Opportunity(
        "devfolio-hackathons", "Devfolio hackathon listings", "Devfolio",
        "hackathon", "india", "college", "https://devfolio.co/hackathons",
        "A directory of open and upcoming hackathons, many organised by Indian colleges and student communities.",
        "Listings change weekly.",
        ("team", "directory"),
    ),
    Opportunity(
        "nasa-space-apps", "NASA International Space Apps Challenge", "NASA and partner space agencies",
        "hackathon", "global", "everyone", "https://www.spaceappschallenge.org/",
        "A global hackathon built around open space and Earth-science data, held at local events and online.",
        "Annual.",
        ("open data", "science", "team"),
    ),
    Opportunity(
        "imagine-cup", "Microsoft Imagine Cup", "Microsoft",
        "hackathon", "global", "college", "https://imaginecup.microsoft.com/",
        "A competition for student founders building a technology product or startup, with mentoring and judging rounds.",
        "Annual competition cycle.",
        ("startup", "product"),
    ),
    # --- Programming contests ----------------------------------------------
    Opportunity(
        "icpc", "International Collegiate Programming Contest (ICPC)", "ICPC Foundation",
        "contest", "global", "college", "https://icpc.global/",
        "The best-known team programming contest for university students: regional rounds lead to a world final.",
        "Annual season of regional contests.",
        ("algorithms", "team of three"),
    ),
    Opportunity(
        "indian-computing-olympiad", "Indian Computing Olympiad", "IARCS",
        "contest", "india", "school", "https://www.iarcs.org.in/inoi/",
        "The national olympiad that selects India's team for the International Olympiad in Informatics. "
        "Open to school students up to class 12.",
        "Annual; zonal rounds lead to INOI and a training camp.",
        ("algorithms", "olympiad", "C++"),
    ),
    Opportunity(
        "codeforces", "Codeforces rounds", "Codeforces",
        "contest", "global", "everyone", "https://codeforces.com/contests",
        "Rated competitive-programming rounds across several difficulty divisions, with editorials afterwards.",
        "Several rounds most weeks.",
        ("algorithms", "rated", "online"),
    ),
    Opportunity(
        "codechef", "CodeChef contests", "CodeChef",
        "contest", "india", "everyone", "https://www.codechef.com/contests",
        "Weekly rated contests with divisions for beginners, plus practice problems sorted by difficulty.",
        "Weekly.",
        ("algorithms", "rated", "beginner-friendly"),
    ),
    Opportunity(
        "atcoder", "AtCoder contests", "AtCoder",
        "contest", "global", "everyone", "https://atcoder.jp/contests/",
        "Regular contests including the AtCoder Beginner Contest, known for clean, well-tested problems.",
        "Most weekends.",
        ("algorithms", "rated", "beginner-friendly"),
    ),
    Opportunity(
        "kaggle-competitions", "Kaggle competitions", "Kaggle",
        "contest", "global", "everyone", "https://www.kaggle.com/competitions",
        "Data-science and machine-learning competitions, including beginner \"Getting Started\" problems.",
        "Rolling; some competitions never close.",
        ("data science", "machine learning"),
    ),
    # --- Open source -------------------------------------------------------
    Opportunity(
        "gsoc", "Google Summer of Code", "Google",
        "open-source", "global", "everyone", "https://summerofcode.withgoogle.com/",
        "A mentored, remote programme where contributors new to open source work on a project with an open-source "
        "organisation. Check the official eligibility rules for your cycle.",
        "Annual; organisations are announced before the contributor application window.",
        ("mentorship", "remote", "stipend"),
    ),
    Opportunity(
        "outreachy", "Outreachy internships", "Software Freedom Conservancy",
        "open-source", "global", "everyone", "https://www.outreachy.org/",
        "Paid, remote open-source internships for people subject to systemic bias or underrepresented in tech.",
        "Two cohorts a year.",
        ("mentorship", "remote", "inclusion"),
    ),
    Opportunity(
        "lfx-mentorship", "LFX Mentorship", "The Linux Foundation",
        "open-source", "global", "everyone", "https://mentorship.lfx.linuxfoundation.org/",
        "Structured mentorships on Linux Foundation projects, from the Linux kernel to cloud-native tooling.",
        "Several terms a year.",
        ("mentorship", "linux", "cloud native"),
    ),
    Opportunity(
        "mlh-fellowship", "MLH Fellowship", "Major League Hacking (MLH)",
        "open-source", "global", "college", "https://fellowship.mlh.com/",
        "A remote, twelve-week programme in which small groups contribute to real open-source and partner projects.",
        "Multiple batches a year.",
        ("remote", "team", "stipend"),
    ),
    Opportunity(
        "hacktoberfest", "Hacktoberfest", "DigitalOcean",
        "open-source", "global", "everyone", "https://hacktoberfest.com/",
        "A month-long event every October that encourages first contributions to open-source repositories.",
        "Every October.",
        ("first contribution", "beginner-friendly"),
    ),
    # --- Scholarships and fellowships ---------------------------------------
    Opportunity(
        "national-scholarship-portal", "National Scholarship Portal", "Government of India",
        "scholarship", "india", "college", "https://scholarships.gov.in/",
        "The single portal for central-government scholarship schemes, including AICTE's Pragati and Saksham "
        "schemes for technical-education students, plus many state schemes.",
        "Applications open once a year per scheme.",
        ("government", "need-based", "merit"),
    ),
    Opportunity(
        "reliance-foundation", "Reliance Foundation Scholarships", "Reliance Foundation",
        "scholarship", "india", "college", "https://www.scholarships.reliancefoundation.org/",
        "Undergraduate and postgraduate scholarships for students in India, selected on merit and other criteria "
        "published on the official site.",
        "Annual application cycle.",
        ("undergraduate", "postgraduate"),
    ),
    Opportunity(
        "fulbright-nehru", "Fulbright-Nehru Fellowships", "United States-India Educational Foundation (USIEF)",
        "scholarship", "india", "college", "https://www.usief.org.in/",
        "Fellowships for Indian citizens to study, research or teach in the United States, including master's "
        "and doctoral programmes.",
        "Annual competition.",
        ("study abroad", "postgraduate"),
    ),
    Opportunity(
        "chevening", "Chevening Scholarships", "UK Government (FCDO)",
        "scholarship", "global", "college", "https://www.chevening.org/",
        "Fully funded one-year master's scholarships in the UK for applicants with leadership potential.",
        "Annual; applications usually open in the second half of the year.",
        ("study abroad", "master's"),
    ),
    Opportunity(
        "daad", "DAAD scholarship database", "German Academic Exchange Service (DAAD)",
        "scholarship", "global", "college", "https://www.daad.de/en/study-and-research-in-germany/scholarships/",
        "A searchable database of scholarships for international students and researchers in Germany.",
        "Rolling; each scholarship has its own deadline.",
        ("study abroad", "research", "directory"),
    ),
    # --- Internships and student benefits ------------------------------------
    Opportunity(
        "aicte-internship-portal", "National Internship Portal", "AICTE, Ministry of Education",
        "internship", "india", "college", "https://internship.aicte-india.org/",
        "A government portal listing internships with ministries, PSUs, state governments and companies for "
        "students of AICTE- and UGC-recognised institutions.",
        "Listings are added continuously.",
        ("government", "industry"),
    ),
    Opportunity(
        "github-student-pack", "GitHub Student Developer Pack", "GitHub",
        "internship", "global", "college", "https://education.github.com/pack",
        "Free access to developer tools and services for verified students, useful for building portfolio projects.",
        "Available year-round with student verification.",
        ("tools", "free", "portfolio"),
    ),
    Opportunity(
        "nptel", "NPTEL online courses and certification", "IITs and IISc (NPTEL)",
        "internship", "india", "everyone", "https://nptel.ac.in/",
        "Free engineering and science courses from IIT and IISc faculty, with an optional proctored certification exam.",
        "New course runs each semester.",
        ("courses", "certification", "free"),
    ),
)


def all_opportunities() -> list[dict]:
    return [item.as_dict() for item in OPPORTUNITIES]


def category_counts() -> list[dict]:
    counts = {key: 0 for key in CATEGORIES}
    for item in OPPORTUNITIES:
        counts[item.category] += 1
    return [{"key": key, "label": CATEGORIES[key], "count": counts[key]} for key in CATEGORIES]


def validate() -> None:
    """Raise ``ValueError`` if any entry breaks the editorial rules above."""
    seen: set[str] = set()
    for item in OPPORTUNITIES:
        if item.slug in seen:
            raise ValueError(f"duplicate opportunity slug {item.slug}")
        seen.add(item.slug)
        if item.category not in CATEGORIES:
            raise ValueError(f"{item.slug}: unknown category {item.category}")
        if item.region not in REGIONS:
            raise ValueError(f"{item.slug}: unknown region {item.region}")
        if item.audience not in AUDIENCES:
            raise ValueError(f"{item.slug}: unknown audience {item.audience}")
        if not item.url.startswith("https://"):
            raise ValueError(f"{item.slug}: official links must be HTTPS")
        if not item.summary or not item.organiser:
            raise ValueError(f"{item.slug}: summary and organiser are required")
