from dataclasses import dataclass, asdict
from typing import Dict, Optional, Sequence

from sqlalchemy import inspect, text

try:
    from backend.ai.next_event_common import is_supported_league, normalize_text
except ImportError:
    from ai.next_event_common import is_supported_league, normalize_text


XG_SCOPE = "Top 5 leagues + UEFA Champions League"

SHOT_TABLE_CANDIDATES: Sequence[str] = (
    "shot_events",
    "match_shots",
    "shots",
)

REQUIRED_TRUE_XG_COLUMNS = {
    "match_id",
    "team_id",
    "minute",
    "x",
    "y",
    "is_goal",
}

OPTIONAL_TRUE_XG_COLUMNS = {
    "shot_type",
    "body_part",
    "assist_type",
    "under_pressure",
}


@dataclass
class XGGranularity:
    mode: str
    reason: str
    shot_table: Optional[str] = None
    row_count: int = 0
    required_columns_present: bool = False
    optional_context_columns: Optional[Sequence[str]] = None

    @property
    def is_proxy(self) -> bool:
        return self.mode != "true_xg"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _safe_scalar_int(db, statement: str) -> int:
    try:
        value = db.execute(text(statement)).scalar()
        return int(value or 0)
    except Exception:
        return 0


def detect_xg_granularity(db, min_true_rows: int = 300) -> XGGranularity:
    engine = getattr(db, "bind", None)
    if engine is None:
        return XGGranularity(
            mode="xg_proxy",
            reason="Database bind is unavailable; defaulting to aggregate-statistics xG proxy.",
        )

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    for table_name in SHOT_TABLE_CANDIDATES:
        if table_name not in table_names:
            continue

        try:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
        except Exception:
            continue

        missing_required = REQUIRED_TRUE_XG_COLUMNS - columns
        if missing_required:
            return XGGranularity(
                mode="xg_proxy",
                reason=(
                    "Shot table was found but does not expose the minimum true-xG schema. "
                    f"Missing columns: {sorted(missing_required)}"
                ),
                shot_table=table_name,
                required_columns_present=False,
                optional_context_columns=sorted(columns & OPTIONAL_TRUE_XG_COLUMNS),
            )

        row_count = _safe_scalar_int(db, f"SELECT COUNT(*) FROM {table_name}")
        if row_count < min_true_rows:
            return XGGranularity(
                mode="xg_proxy",
                reason=(
                    "Shot-level schema exists but sample size is too small for a stable true xG model. "
                    f"rows={row_count}, required_min_rows={min_true_rows}."
                ),
                shot_table=table_name,
                row_count=row_count,
                required_columns_present=True,
                optional_context_columns=sorted(columns & OPTIONAL_TRUE_XG_COLUMNS),
            )

        return XGGranularity(
            mode="true_xg",
            reason="Shot-level coordinates and outcomes are available; training true xG pipeline.",
            shot_table=table_name,
            row_count=row_count,
            required_columns_present=True,
            optional_context_columns=sorted(columns & OPTIONAL_TRUE_XG_COLUMNS),
        )

    return XGGranularity(
        mode="xg_proxy",
        reason=(
            "No shot-level table with coordinates was found; using aggregate match statistics "
            "(shots, possession, corners, events) for an explicitly labeled xG proxy."
        ),
    )
