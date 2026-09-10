# coding: utf-8
"""Fix openjiuwen's inverted BM25 rank-to-score transform.

SQLite FTS5 exposes match quality in the ``rank`` column as a **negative**
number, where more negative is a better match -- which is why the kernel's own
keyword query says ``ORDER BY rank`` with no ``DESC``. The transform that turns
that rank into a 0-1 score reads::

    def bm25_rank_to_score(rank: float) -> float:
        if rank >= 0:
            return 1.0 / (1.0 + rank)
        return 1.0 / (1.0 - rank)          # == 1 / (1 + |rank|)

So the better the match, the larger ``|rank|`` and the *smaller* the score. The
ordering is inverted, and the SQL ordering and the score disagree with each
other about the same rows.

Why that is not cosmetic. ``search`` merges the two channels as
``0.7 * vector + 0.3 * text`` and keeps rows scoring at least ``min_score``,
0.7 by default. A strong keyword hit at rank -3.8 scores 0.21 under the stock
transform and contributes 0.06 to the merge, so a document matching well on
both channels lands at 0.62 and is filtered out -- *because* its keyword match
was good. Corrected, the same row contributes 0.24 and clears the floor.

The symptom was noticed but read as a property of BM25 rather than a defect:
the kernel comments that "pure-keyword BM25 scores run low (trigram multi-token
queries commonly land 0.1-0.3 after the rank->score transform)" and compensates
with a separate, lower ``keywordMinScore`` floor of 0.1 on the no-embeddings
path. That range is exactly what an inverted transform yields for good matches.

The replacement maps match strength monotonically into [0, 1):

    strength = -rank ;  score = strength / (1 + strength)

Zero strength scores 0, a rank of -3.8 scores 0.79, and no score can reach 1,
so the value stays comparable with the cosine similarities on the vector side.
A non-negative rank carries no match strength and scores 0; FTS5 does not return
one for a matching row.

**Both bindings must be rebound.** ``manager.py`` imports the function by name at
module level (``from .internal import bm25_rank_to_score``), so patching only the
``internal`` module would leave the manager calling the original and the patch
would silently do nothing.

Applied once per process from ``JiuWenSwarmDeepAdapter.__init__``. Remove this
module once upstream corrects the transform.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = ["apply_bm25_score_patch", "bm25_rank_to_score"]

_PATCHED = False


def bm25_rank_to_score(rank: float) -> float:
    """Map an FTS5 ``rank`` to a 0-1 score that grows with match quality."""
    strength = -float(rank)
    if strength <= 0.0:
        # No match strength. FTS5 returns negative ranks for hits, so this is
        # either a non-hit or a caller passing an already-positive score.
        return 0.0
    return strength / (1.0 + strength)


def apply_bm25_score_patch() -> None:
    """Rebind the rank-to-score transform in the kernel. Idempotent per process."""
    global _PATCHED
    if _PATCHED:
        return

    from openjiuwen.core.memory.lite import internal as lite_internal
    from openjiuwen.core.memory.lite import manager as lite_manager

    for module in (lite_internal, lite_manager):
        if not hasattr(module, "bm25_rank_to_score"):
            # Fail loudly rather than silently no-op: a rename upstream most likely
            # means the transform was fixed and this module should be deleted, but it
            # could also mean the patch is quietly no longer applied.
            raise AttributeError(
                f"bm25_score_patch expected {module.__name__}.bm25_rank_to_score; "
                "upstream has changed. Re-check whether this patch is still needed."
            )

    _PATCHED = True
    lite_internal.bm25_rank_to_score = bm25_rank_to_score
    lite_manager.bm25_rank_to_score = bm25_rank_to_score
    logger.info("[bm25-score] patched the inverted FTS5 rank-to-score transform")
