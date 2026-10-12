"""Regenerate tests/fixtures/toy1.json and toy2.json (PLAN.md appendices A, B)."""
import os

from .instance import Instance, save_instance

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "fixtures")


def toy1(alpha=2, beta=10) -> Instance:
    a0 = {("s", "c"): 2, ("s", "v"): 8, ("v", "c"): 1, ("c", "d1"): 1, ("c", "d2"): 1,
          ("s", "d1"): 10, ("s", "d2"): 10}
    a1 = {k: w for k, w in a0.items() if k != ("s", "c")}
    return Instance(T=2, nodes=["s", "v", "c", "d1", "d2"], s="s", D=["d1", "d2"], C=["c"],
                    arcs=[a0, a1], f=[1, 1], g={("c", 0): 1, ("c", 1): 1},
                    alpha=alpha, beta=beta, scale=1, meta={"name": "toy1"})


def toy2() -> Instance:
    a = {("s", "a"): 2, ("a", "d1"): 2, ("a", "d2"): 2, ("s", "d1"): 5, ("s", "d2"): 5}
    return Instance(T=1, nodes=["s", "a", "d1", "d2"], s="s", D=["d1", "d2"], C=[],
                    arcs=[a], f=[1], g={}, alpha=1, beta=1, scale=1, meta={"name": "toy2"})


if __name__ == "__main__":
    os.makedirs(FIX, exist_ok=True)
    save_instance(toy1(), os.path.join(FIX, "toy1.json"))
    save_instance(toy2(), os.path.join(FIX, "toy2.json"))
