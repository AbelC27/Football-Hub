import re
from typing import Optional

SUPPORTED_COMPETITION_LEAGUE_IDS = {
    39,    # Premier League (API-Football)
    140,   # La Liga (API-Football)
    78,    # Bundesliga (API-Football)
    135,   # Serie A (API-Football)
    61,    # Ligue 1 (API-Football)
    4480,  # Champions League (TheSportsDB)
    2021,  # Premier League (football-data.org)
    2014,  # La Liga (football-data.org)
    2002,  # Bundesliga (football-data.org)
    2019,  # Serie A (football-data.org)
    2015,  # Ligue 1 (football-data.org)
    2001,  # Champions League (football-data.org)
}

SUPPORTED_LEAGUE_NAME_TOKENS = (
    "premier league",
    "la liga",
    "bundesliga",
    "serie a",
    "ligue 1",
    "champions league",
)

FINISHED_MATCH_STATUSES = {"FT", "AET", "PEN"}
GOAL_EVENT_TOKENS = ("goal",)
CARD_EVENT_TOKENS = ("card",)
SUBSTITUTION_EVENT_TOKENS = ("subst", "substit")

ASSIST_PATTERN = re.compile(r"assist(?:ed)?\s*[:\-]?\s*([A-Za-z0-9 .'-]+)", re.IGNORECASE)
SUB_OUT_PATTERN = re.compile(r"\bfor\b\s+([A-Za-z0-9 .'-]+)", re.IGNORECASE)


def normalize_text(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def is_supported_league(league) -> bool:
    if not league:
        return False

    if getattr(league, "id", None) in SUPPORTED_COMPETITION_LEAGUE_IDS:
        return True

    league_name = normalize_text(getattr(league, "name", ""))
    return any(token in league_name for token in SUPPORTED_LEAGUE_NAME_TOKENS)


def is_goal_event(event_type: Optional[str]) -> bool:
    normalized = normalize_text(event_type)
    return any(token in normalized for token in GOAL_EVENT_TOKENS)


def is_card_event(event_type: Optional[str]) -> bool:
    normalized = normalize_text(event_type)
    return any(token in normalized for token in CARD_EVENT_TOKENS)


def is_substitution_event(event_type: Optional[str]) -> bool:
    normalized = normalize_text(event_type)
    return any(token in normalized for token in SUBSTITUTION_EVENT_TOKENS)


def is_red_card_detail(detail: Optional[str]) -> bool:
    normalized = normalize_text(detail)
    return "red" in normalized


def extract_assist_name(detail: Optional[str]) -> Optional[str]:
    if not detail:
        return None

    match = ASSIST_PATTERN.search(detail)
    if not match:
        return None

    value = match.group(1).strip()
    return value or None


def extract_sub_out_name(detail: Optional[str]) -> Optional[str]:
    if not detail:
        return None

    match = SUB_OUT_PATTERN.search(detail)
    if not match:
        return None

    value = match.group(1).strip()
    return value or None
