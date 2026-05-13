import asyncio

from neural_grid_signal.config import Settings
from neural_grid_signal.openai_decider import OpenAIGridDecider


def test_openai_decider_skips_when_config_missing():
    decider = OpenAIGridDecider(Settings())

    result = asyncio.run(decider.review([]))

    assert result.enabled is False
    assert result.reason == "missing_openai_config"
