"""Role definitions (Epic 5, Story 5.1) — one file per role, all 11 roles.

Role names match the 1080's /feeds/{role} (analyze/feeds.py ROLE_META).
The Team Lead is the orchestrator (formation, relay, synthesis); the other
ten are pod members.
"""
from team.roles import (  # noqa: F401
    challenger,
    data_analyst,
    data_engineer,
    data_scientist,
    economist,
    financial_analyst,
    mle,
    portfolio_manager,
    quant,
    risk_manager,
    team_lead,
)
from team.roles.challenger import ROLE as CHALLENGER
from team.roles.data_analyst import ROLE as DATA_ANALYST
from team.roles.data_engineer import ROLE as DATA_ENGINEER
from team.roles.data_scientist import ROLE as DATA_SCIENTIST
from team.roles.economist import ROLE as ECONOMIST
from team.roles.financial_analyst import ROLE as FINANCIAL_ANALYST
from team.roles.mle import ROLE as MLE
from team.roles.portfolio_manager import ROLE as PORTFOLIO_MANAGER
from team.roles.quant import ROLE as QUANT
from team.roles.risk_manager import ROLE as RISK_MANAGER
from team.roles.team_lead import ROLE as TEAM_LEAD

ROLES = {
    "team_lead": TEAM_LEAD,
    "data_engineer": DATA_ENGINEER,
    "data_analyst": DATA_ANALYST,
    "data_scientist": DATA_SCIENTIST,
    "financial_analyst": FINANCIAL_ANALYST,
    "economist": ECONOMIST,
    "risk_manager": RISK_MANAGER,
    "challenger": CHALLENGER,
    "portfolio_manager": PORTFOLIO_MANAGER,
    "mle": MLE,
    "quant": QUANT,
}


def get_role(name: str) -> dict:
    if name not in ROLES:
        raise KeyError(f"unknown role: {name!r} (defined: {sorted(ROLES)})")
    return ROLES[name]


def all_roles() -> list[str]:
    return list(ROLES)
