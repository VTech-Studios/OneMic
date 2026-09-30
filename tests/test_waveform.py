import numpy as np

from onemic.domain.waveform import SILENT_COLUMN, WaveColumn, summarise


def test_summarise_keeps_the_lowest_and_highest_sample_across_channels() -> None:
    block = np.array([[0.1, -0.4], [0.7, 0.2], [-0.2, 0.0]], dtype=np.float32)

    column = summarise(block)

    assert column.low == np.float32(-0.4)
    assert column.high == np.float32(0.7)


def test_summarise_of_nothing_is_silence() -> None:
    assert summarise(np.zeros((0, 2), dtype=np.float32)) == SILENT_COLUMN


def test_peak_is_the_larger_excursion_either_side_of_zero() -> None:
    assert WaveColumn(-0.9, 0.3).peak == 0.9
    assert WaveColumn(-0.1, 0.6).peak == 0.6
