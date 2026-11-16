"""B2: B1 + producer-side summary every p seconds, k reports clubbed into one notification."""
import itertools

import numpy as np

from ..prereg import B2_K, B2_P, SUMMARIES
from ..producers import constant_p_win
from .base import Collection


def b2(n_ue, T, p, k, summary):
    p_win = constant_p_win(n_ue, T, p)
    reps = T // p
    n_rep = np.full(n_ue, reps, dtype=np.int64)
    n_notif = np.full(n_ue, -(-reps // k), dtype=np.int64)
    return Collection("B2", {"p": p, "k": k, "summary": summary}, p_win, SUMMARIES[summary],
                      n_notif, n_rep, n_subs=1, max_delay_s=k * p)


def b2_grid():
    """All 5 x 3 x 3 = 45 preregistered B2 settings as (p, k, summary)."""
    return list(itertools.product(B2_P, B2_K, SUMMARIES))
