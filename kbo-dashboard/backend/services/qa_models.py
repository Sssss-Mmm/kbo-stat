"""Only these bounded analysis operations can be selected by the language model."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from security import CURRENT_YEAR


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["team", "player", "clarify", "unsupported"]
    season: int = Field(ge=1982, le=CURRENT_YEAR)
    teams: list[str] = Field(default_factory=list, max_length=3)
    players: list[str] = Field(default_factory=list, max_length=3)
    role: Literal["hitter", "pitcher"] = "hitter"
    metric: Literal["OPS", "AVG", "HR", "RBI", "WAR", "WARProxy", "wRC+", "ERA", "WHIP", "SO", "W", "SV", "HLD"] = "OPS"
    period: Literal["all", "recent", "month", "range"] = "all"
    recent_games: int = Field(default=10, ge=1, le=50)
    month: int | None = Field(default=None, ge=1, le=12)
    start_date: str | None = None
    end_date: str | None = None
    split: Literal["all", "home", "away", "compare"] = "all"
    opponent: str | None = None
    qualified_only: bool = True
    clarification: str = ""


class AnalysisAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=200)
    summary: str = Field(max_length=1800)
    bullets: list[str] = Field(max_length=6)
    limitations: list[str] = Field(max_length=4)
    followups: list[str] = Field(max_length=3)
    evidence_ids: list[str] = Field(min_length=1, max_length=30, description="Used evidence IDs without brackets, e.g. ['E1', 'E2']")
