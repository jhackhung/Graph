"""Instance / Solution data structures, validation and JSON I/O (PLAN.md section 2)."""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field

Arc = tuple[str, str] # directed graph


class InstanceError(ValueError):
    """Raised by validate_instance when an instance violates the problem definition."""


@dataclass
class Instance:
    T: int
    nodes: list[str]
    s: str
    D: list[str]
    C: list[str]
    arcs: list[dict[Arc, int]]          # arcs[t][(u, v)] = positive integer weight
    f: list[int]                        # f[t]
    g: dict[tuple[str, int], int]       # g[(c, t)] >= 0, in 1/scale units
    alpha: int
    beta: int
    scale: int = 1
    meta: dict = field(default_factory=dict)


@dataclass
class Solution:
    arcs: list[set[Arc]]
    mu: dict[tuple[str, int], int]
    origin: dict[tuple[str, int], str]
    path: dict[tuple[str, int], list[Arc]]


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def reachable(arcs, s: str) -> set[str]:
    """Nodes reachable from s using the given arcs (iterable of (u, v))."""
    adj: dict[str, list[str]] = {}
    for u, v in arcs:
        adj.setdefault(u, []).append(v)
    seen = {s}
    q = deque([s])
    while q:
        u = q.popleft()
        for v in adj.get(u, ()):
            if v not in seen:
                seen.add(v)
                q.append(v)
    return seen


def validate_instance(inst: Instance) -> None:
    """Raise InstanceError describing the first violation found."""

    def bad(msg):
        raise InstanceError(msg)

    if not _is_int(inst.T) or inst.T < 1:
        bad(f"T must be a positive int, got {inst.T!r}")
    if not _is_int(inst.alpha) or not _is_int(inst.beta):
        bad(f"alpha and beta must be ints, got alpha={inst.alpha!r}, beta={inst.beta!r}")
    if inst.alpha < 0 or inst.beta < 0:
        bad("alpha and beta must be non-negative")
    if not _is_int(inst.scale) or inst.scale < 1:
        bad("scale must be a positive int")
    if len(set(inst.nodes)) != len(inst.nodes):
        bad("duplicate nodes")
    nodes = set(inst.nodes)
    S, Dset, Cset = {inst.s}, set(inst.D), set(inst.C)
    if len(Dset) != len(inst.D) or len(Cset) != len(inst.C):
        bad("duplicate entries in D or C")
    if not Dset:
        bad("D must be non-empty")
    if (S & Dset) or (S & Cset) or (Dset & Cset):
        bad("s, D, C must be pairwise disjoint")
    if not (S | Dset | Cset) <= nodes:
        bad("s, D, C must be subsets of nodes")
    if len(inst.arcs) != inst.T or len(inst.f) != inst.T:
        bad("arcs and f must have length T")
    for t, fv in enumerate(inst.f):
        if not _is_int(fv) or fv < 1:
            bad(f"f[{t}] must be a positive int")
    for c in inst.C:
        for t in range(inst.T):
            gv = inst.g.get((c, t))
            if gv is None or not _is_int(gv) or gv < 0:
                bad(f"g[({c},{t})] must be a non-negative int")
    for t, arcs in enumerate(inst.arcs):
        for (u, v), w in arcs.items():
            if u not in nodes or v not in nodes:
                bad(f"slot {t}: arc {u}->{v} has unknown endpoint")
            if u == v:
                bad(f"slot {t}: self loop {u}->{v}")
            if not _is_int(w) or w < 1:
                bad(f"slot {t}: weight of {u}->{v} must be a positive int, got {w!r}")
            if v == inst.s:
                bad(f"slot {t}: arc {u}->{v} enters the source")
            if u in Dset:
                bad(f"slot {t}: arc {u}->{v} leaves destination {u}")
        reach = reachable(arcs, inst.s)
        for d in inst.D:
            if d not in reach:
                bad(f"slot {t}: destination {d} not reachable from source")


# ---------------------------------------------------------------- JSON I/O

def _enc_arc(a: Arc) -> str:
    return f"{a[0]}->{a[1]}"


def _dec_arc(k: str) -> Arc:
    u, v = k.split("->")
    return (u, v)


def _enc_key(k: tuple[str, int]) -> str:
    return f"{k[0]}@{k[1]}"


def _dec_key(k: str) -> tuple[str, int]:
    n, t = k.rsplit("@", 1)
    return (n, int(t))


def instance_to_dict(inst: Instance) -> dict:
    return {
        "T": inst.T, "nodes": list(inst.nodes), "s": inst.s,
        "D": list(inst.D), "C": list(inst.C),
        "arcs": [{_enc_arc(a): w for a, w in sorted(arcs.items())} for arcs in inst.arcs],
        "f": list(inst.f),
        "g": {_enc_key(k): v for k, v in sorted(inst.g.items())},
        "alpha": inst.alpha, "beta": inst.beta, "scale": inst.scale,
        "meta": inst.meta,
    }


def instance_from_dict(d: dict) -> Instance:
    return Instance(
        T=d["T"], nodes=list(d["nodes"]), s=d["s"], D=list(d["D"]), C=list(d["C"]),
        arcs=[{_dec_arc(k): w for k, w in arcs.items()} for arcs in d["arcs"]],
        f=list(d["f"]),
        g={_dec_key(k): v for k, v in d.get("g", {}).items()},
        alpha=d["alpha"], beta=d["beta"], scale=d.get("scale", 1),
        meta=d.get("meta", {}),
    )


def solution_to_dict(sol: Solution) -> dict:
    return {
        "arcs": [sorted(_enc_arc(a) for a in arcs) for arcs in sol.arcs],
        "mu": {_enc_key(k): v for k, v in sorted(sol.mu.items())},
        "origin": {_enc_key(k): v for k, v in sorted(sol.origin.items())},
        "path": {_enc_key(k): [_enc_arc(a) for a in p] for k, p in sorted(sol.path.items())},
    }


def solution_from_dict(d: dict) -> Solution:
    return Solution(
        arcs=[{_dec_arc(k) for k in arcs} for arcs in d["arcs"]],
        mu={_dec_key(k): v for k, v in d["mu"].items()},
        origin={_dec_key(k): v for k, v in d["origin"].items()},
        path={_dec_key(k): [_dec_arc(a) for a in p] for k, p in d["path"].items()},
    )


def save_instance(inst: Instance, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(instance_to_dict(inst), fh, ensure_ascii=False, indent=1)


def load_instance(path: str) -> Instance:
    """Load an Instance JSON. Fixtures lacking 'nodes'/'g' (e.g. fig1.json) are completed
    from the arcs; g defaults to 0 only when the file marks it unknown."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if "nodes" not in d:
        ns = {d["s"], *d["D"], *d["C"]}
        for arcs in d["arcs"]:
            for k in arcs:
                ns.update(_dec_arc(k))
        d["nodes"] = sorted(ns)
    return instance_from_dict(d)


def save_solution(sol: Solution, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(solution_to_dict(sol), fh, indent=1)


def load_solution(path: str) -> Solution:
    with open(path, encoding="utf-8") as fh:
        return solution_from_dict(json.load(fh))
