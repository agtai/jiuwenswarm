from __future__ import annotations

import pytest

from jiuwenswarm.agents.harness.common.memory.internal import (
    bm25_rank_to_score as ours,
)
from jiuwenswarm.server.runtime.memory.bm25_score_patch import (
    apply_bm25_score_patch,
    bm25_rank_to_score as fixed,
)

# FTS5's bm25() returns negative values and more negative is a better match.
BETTER, WORSE = -8.0, -1.5


def _kernel_fn():
    from openjiuwen.core.memory.lite import manager

    return manager.bm25_rank_to_score


@pytest.mark.parametrize("fn_name", ["fixed", "ours"])
def test_a_better_match_scores_higher(fn_name):
    """The whole defect in one assertion.

    The stock transform is 1/(1+|rank|), so the score *falls* as the match improves.
    Downstream that is not merely cosmetic: the hybrid path weights the lexical
    channel at 0.3 and filters the merged score at 0.7, so an inverted score makes a
    strong keyword hit contribute less than a weak one.
    """
    fn = {"fixed": fixed, "ours": ours}[fn_name]
    assert fn(BETTER) > fn(WORSE)


@pytest.mark.parametrize("fn_name", ["fixed", "ours"])
def test_scores_stay_within_zero_and_one(fn_name):
    fn = {"fixed": fixed, "ours": ours}[fn_name]
    for rank in (-0.001, -1.0, -50.0, -1e6):
        assert 0.0 <= fn(rank) < 1.0


@pytest.mark.parametrize("fn_name", ["fixed", "ours"])
def test_no_match_strength_scores_zero(fn_name):
    """rank 0 carries no signal, and FTS5 never returns a positive rank for a hit."""
    fn = {"fixed": fixed, "ours": ours}[fn_name]
    assert fn(0.0) == 0.0
    assert fn(3.0) == 0.0


@pytest.mark.parametrize("fn_name", ["fixed", "ours"])
def test_the_ordering_matches_sql_order_by_rank(fn_name):
    """Scores must rank the same way ORDER BY rank already does."""
    fn = {"fixed": fixed, "ours": ours}[fn_name]
    ranks = [-9.4, -6.1, -3.8, -3.6, -0.9]  # SQL order: best first
    scores = [fn(r) for r in ranks]
    assert scores == sorted(scores, reverse=True)


def test_a_strong_hit_now_clears_the_hybrid_floor():
    """Why this matters downstream, in the kernel's own numbers.

    Hybrid merges 0.7*vector + 0.3*text and keeps results scoring >= 0.7. With the
    inverted transform a document matching well on both channels still fell under the
    floor, purely because its keyword score was small *because* the match was good.
    """
    vector = 0.80
    strong_rank = -3.8

    stock_text = 1.0 / (1.0 - strong_rank)  # the upstream transform
    assert 0.7 * vector + 0.3 * stock_text < 0.7  # filtered out, wrongly

    assert 0.7 * vector + 0.3 * fixed(strong_rank) >= 0.7  # kept


def test_patch_rebinds_the_name_the_manager_actually_calls():
    """manager.py does `from .internal import bm25_rank_to_score` at module level.

    Patching only openjiuwen...internal would leave that binding untouched and the
    patch would silently do nothing, so the manager's own name must be rebound.
    """
    apply_bm25_score_patch()
    assert _kernel_fn()(BETTER) > _kernel_fn()(WORSE)


def test_applying_twice_is_a_no_op():
    apply_bm25_score_patch()
    apply_bm25_score_patch()
    assert _kernel_fn()(BETTER) > _kernel_fn()(WORSE)
