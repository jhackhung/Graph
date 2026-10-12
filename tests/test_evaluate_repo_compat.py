"""Phase 2 (4): repo_compat regression against the repo's own numbers (fixture from seed 42 trial)."""
import json
import os

import pytest

from ilp.evaluate import evaluate_repo_compat

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "repo_trial_seed42.json")
EXPECT = {"raw": (51.2366, 1.7241, 2.0, 79.8572), "optimal": (51.2975, 0.8621, 1.5, 70.6078)}


@pytest.mark.parametrize("variant", sorted(EXPECT))
def test_repo_compat_matches_report_and_repo(variant):
    d = json.load(open(FIX, encoding="utf-8"))
    m = d["meta"]
    got = evaluate_repo_compat(d[variant]["trees"], m["caches"], m["src"], m["alpha"], m["beta"],
                               m["hit_factor"])
    assert got == pytest.approx(EXPECT[variant], abs=1e-3)
    assert got == pytest.approx(tuple(d[variant]["ref"]), abs=1e-9)   # TVM.evaluate_algorithm output
