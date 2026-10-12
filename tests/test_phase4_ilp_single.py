"""Phase 4: ILP, single slot, no cache. Random seeds 1000..1049."""
import pytest

from ilp.gen_random import gen_instance
from ilp.make_toys import toy2
from tests.ilp_helpers import check_ilp


def test_toy2_shared_link_once():
    res, ev = check_ilp(toy2(), use_cache=False)
    assert res["objective"] == 6          # 8 would mean cost is charged on y instead of x


@pytest.mark.parametrize("seed", range(1000, 1050))
def test_random_matches_brute(seed):
    inst = gen_instance(seed, T=1)
    check_ilp(inst, use_cache=False)
