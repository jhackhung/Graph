"""Random tiny-instance generator (PLAN.md appendix C). Same seed -> same instance."""
from __future__ import annotations

import random

from .instance import Instance, InstanceError, validate_instance


def _perturb(rng, arcs, general, cand_nodes, s, D, n_change=None):
    """Return a copy of arcs with 1-2 weights changed and (50%) one arc toggled."""
    new = dict(arcs)
    keys = sorted(new)
    for k in rng.sample(keys, min(len(keys), n_change or rng.randint(1, 2))):
        new[k] = rng.randint(1, 9)
    if rng.random() < 0.5:
        u = rng.choice([x for x in cand_nodes])
        v = rng.choice([x for x in cand_nodes + D if x != u])
        if (u, v) in new:
            if len(new) > 1:
                del new[(u, v)]
        else:
            new[(u, v)] = rng.randint(1, 9)
    return new


def gen_instance(seed: int, n_nodes=None, nD=None, nC=None, T=None,
                 alpha=None, beta=None, scale: int = 1, n_change=None) -> Instance:
    rng = random.Random(seed)
    nD = nD if nD is not None else rng.randint(1, 3)
    nC = nC if nC is not None else rng.randint(0, 2)
    T = T if T is not None else rng.randint(1, 3)
    if n_nodes is None:
        n_nodes = rng.randint(max(5, 1 + nD + nC), 7)
    n_gen = n_nodes - 1 - nD - nC
    if n_gen < 0:
        raise ValueError("n_nodes too small")
    s = "s"
    D = [f"d{i + 1}" for i in range(nD)]
    C = [f"c{i + 1}" for i in range(nC)]
    G = [f"v{i + 1}" for i in range(n_gen)]
    nodes = [s] + G + C + D
    mid = G + C                      # non-s, non-D nodes
    alpha = alpha if alpha is not None else rng.choice([1, 5])
    beta = beta if beta is not None else rng.choice([0, 1, 5, 50])
    discarded = 0
    while True:
        base = {}
        for i, u in enumerate(mid):
            for v in mid[i + 1:]:
                if rng.random() < 0.5:
                    base[(u, v)] = rng.randint(1, 9)
                    base[(v, u)] = rng.randint(1, 9)
        for v in mid:
            if rng.random() < 0.7:
                base[(s, v)] = rng.randint(1, 9)
        for d in D:
            for u in mid:
                if rng.random() < 0.6:
                    base[(u, d)] = rng.randint(1, 9)
        arcs = [base]
        for _ in range(T - 1):
            arcs.append(_perturb(rng, arcs[-1], G, mid, s, D, n_change))
        g = {(c, t): rng.randint(0, 3) * scale for c in C for t in range(T)}
        inst = Instance(T=T, nodes=nodes, s=s, D=D, C=C, arcs=arcs, f=[1] * T, g=g,
                        alpha=alpha, beta=beta, scale=scale,
                        meta={"seed": seed, "discarded": discarded})
        try:
            validate_instance(inst)
            return inst
        except InstanceError:
            discarded += 1
