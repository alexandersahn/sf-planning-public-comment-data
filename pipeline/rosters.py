"""Curated person-level rosters of organized-interest participants.

Most speakers state their affiliation in only a fraction of their
appearances, so a comment-level rule ("this comment names the Housing Action
Coalition") labels the comment but leaves the same person's other testimony
unlabeled. These rosters attach an affiliation to the *person*, so it carries
across every hearing they spoke at.

Two rosters feed `assign_roles.py`:

  CURATED (here)   hand-collected from organization team/board pages (current
                   and Wayback snapshots, collected 2026-09) plus speakers'
                   own self-identification in the minutes. Highest precedence
                   among person-level evidence.

  DERIVED          built by `build_rosters.py` from the corpus itself: a
                   speaker who states an affiliation in at least one comment
                   is credited with it in their other comments, inside a
                   tenure window. Lower precedence.

Provenance for the pro-housing rosters: ported from the SF pro-housing
presence analysis in Dropbox/Admin/public_facing/yimby_law (roster.py,
2026-09). Housing Action Coalition *board* members (developers and land-use
lawyers, who appear at hearings in their own professional capacity) are
deliberately excluded; staff only. Non-SF chapter and national staff are
excluded.

The dict key is the canonical `name_clean` spelling; the list holds alternate
spellings seen in the minutes.
"""

# ---------------------------------------------------------------- rosters

# SFBARF / SF YIMBY / YIMBY Action — the YIMBY movement proper.
YIMBY = {
    # The minutes render this name by ear and get it wrong more often than
    # right: "Trouss", "Transs", "Kraus". String distance cannot recover
    # these, so they are recorded here, where the merge is auditable.
    # NOT included: "Sonja Kos" / "Sonja Koss", who is a different person —
    # coded Affordable Housing Developer, commenting on PDR loss and formula
    # retail in 2013-14, the opposite side of the issue.
    "Sonja Trauss": ["Sonja Transs", "SonjaTranss", "Sonja Trouss",
                     "Sonja Kraus"],
    "Brian Hanlon": [],
    "Laura Foote": ["Laura Clark", "Laura Clarke", "Laura Foote Clark"],
    "Laura Fingal-Surma": [], "Vincent Woo": [], "Victoria Fierce": [],
    "Skylar Taylor": [], "Joe Rivano Barros": [], "Kyle Borland": [],
    "Milo Trauss": [], "Jane Natoli": [], "Ernest Brown": [],
    "Steven Buss": ["Steven Bacio", "Steven Buss Bacio"],
    "Gillian Pressman": ["Gill Pressman"],
    "Jeff Fong": [], "Parag Gupta": [], "Sasha Aickin": [],
    "Destiny Collins": [], "Rudy Espinoza Murray": ["Rudy Espinoza"],
    "Jessamyn Garner": ["Jae Garner"], "Julia Teitelbaum": [],
    "Rafa Sonnenfeld": [], "Alex Melendrez": [], "Mariah Redfern": [],
    "Brittany Williams": [], "Joanna Gubman": [], "Nikki Yang": [],
    "Nadia Rahman": [], "Nick Pinkston": [], "Courtney Porcella": [],
    "Jaclynn Garry": [], "Amy Klein": [], "Tia Stone": [],
    "Brandon Powell": [], "Chang Sun": [], "Michael Sacks": [],
    "David Broockman": ["David Brockman"],
    "Theo Gordon": [], "Drew Hess": [],  # minutes self-ID
}

# Housing Action Coalition staff and GrowSF. Kept as one bucket because the
# source roster does not resolve individuals between the two organizations.
PRO_HOUSING_OTHER = {
    "Tim Colen": [], "Kate White": [], "Joseph Curtin": [],
    "Jodie Medeiros": [], "Rob Poole": ["Robert Poole"], "Corey Smith": [],
    "Todd David": [], "Nico Nagle": ["Nicholas Nagle"],
    "Mallory Lynn Hill": ["Mallory Hill"], "Kaylé Barnes": ["Kayle Barnes"],
    "Deborah Schneider": [], "Jake Price": [], "Miles Johnson": [],
    "Abbie Tuning": [], "Ali Sapirman": [], "Gabrielle Blavatsky": [],
    "Brianna Morales": ["Breanna Morales"], "Witt Turner": [],
    "Victoria Gomez": [], "Sam Moss": [], "Sachin Agarwal": [],
    "Ryan Brown": [], "Jen Laska": [], "Jan Chong": [], "Carrie Barnes": [],
    "Garry Tan": [], "Leo van den Daele": [], "McKenna Quint": [],
}

CURATED = {
    "YIMBY": YIMBY,
    "Pro-Housing Advocacy": PRO_HOUSING_OTHER,
}

# Earliest year a name match counts, for names common enough that an earlier
# match is more likely a different person than an early appearance.
YEAR_FLOOR = {
    "Victoria Gomez": 2024,
}


def curated_lookup():
    """{lowercased name or alias: (role_long, canonical name)}."""
    out = {}
    for role, people in CURATED.items():
        for canonical, aliases in people.items():
            for n in [canonical] + list(aliases):
                out[n.strip().lower()] = (role, canonical)
    return out


# Roles that describe a *person's* standing affiliation and may therefore be
# carried across hearings. Deliberately excluded: Project Team, DR Team, and
# Legal, which describe someone's relationship to one specific case — an
# architect who sponsored a project in 2009 is not a project sponsor in 2019 —
# and Planning Staff / Commissioner, which the attendance rosters already
# establish per meeting.
PROPAGATABLE_ROLES = {
    "Affordable Housing Developer",
    "Anti-Development",
    "Anti-Displacement",
    "Chamber of Commerce",
    "City Agency",
    "Commercial Association",
    "Community Benefit District",
    "Construction",
    "Historic Preservation",
    "Labor",
    "Neighborhood Association",
    "Pro-Housing Advocacy",
    "Race/Immigration/LGBTQ Groups",
    "Religious",
    "SPUR",
    "Slow Growth",
    "Social Services",
    "Tenant Association",
    "YIMBY",
}
