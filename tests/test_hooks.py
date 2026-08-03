# kept for harness selection; token recording covered in test_harness_tokens.py
from repo_vendor.config import Settings
from repo_vendor.harness import HeuristicHarness, get_harness


def test_heuristic_harness_when_no_key():
    settings = Settings(CURSOR_API_KEY="", ALLOW_LLM_FALLBACK=True)
    h = get_harness(settings)
    assert isinstance(h, HeuristicHarness)
    assert h.name == "heuristic"
