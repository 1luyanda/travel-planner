"""Stable public imports for the ``ranking`` package.

This file lets callers write:

    from ranking import prepare_ranking_records, RankingConstraints

instead of depending on the internal file location:

    from ranking.interface import prepare_ranking_records, RankingConstraints

Keeping public imports here means ``interface.py`` can later be renamed or
split into multiple files without forcing the ranking developer to update
their imports.
"""

# Re-export the parts of interface.py that other project modules may use.
from .interface import (
    CandidatePreparationResult,
    RankedDestination,
    RankingCandidate,
    RankingConstraints,
    RankingDataError,
    RejectedCandidate,
    Rejection,
    prepare_ranking_data,
    prepare_ranking_records,
)
from .ranking import RankingPreferences, rank_candidates, rank_destinations
from .policy import preferences_from_intents

# ``__all__`` documents the supported public API and controls what is exported
# by ``from ranking import *``. Names not listed here should be treated as
# implementation details.
__all__ = [
    "CandidatePreparationResult",
    "RankedDestination",
    "RankingCandidate",
    "RankingConstraints",
    "RankingPreferences",
    "RankingDataError",
    "RejectedCandidate",
    "Rejection",
    "prepare_ranking_data",
    "prepare_ranking_records",
    "preferences_from_intents",
    "rank_destinations",
    "rank_candidates",
]
