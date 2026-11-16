"""B0: T1 and T2 each subscribe; every producer sends one raw 1 s measurement per notification."""
import numpy as np

from ..producers import constant_p_win
from .base import Collection


def b0(n_ue, T):
    p_win = constant_p_win(n_ue, T, 1)
    n = np.full(n_ue, T, dtype=np.int64)
    return Collection("B0", {}, p_win, ("raw",), n, n.copy(), n_subs=2, max_delay_s=1)
