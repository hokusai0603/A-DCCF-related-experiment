"""B1: B0 with A-DCCF de-duplication: one subscription per producer, fanned out to T1 and T2."""
from .b0 import b0


def b1(n_ue, T):
    c = b0(n_ue, T)
    c.family, c.n_subs = "B1", 1
    return c
