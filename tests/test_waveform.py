import numpy as np
import pytest

from onemic.domain.waveform import SILENT_COLUMN, WaveColumn, split_columns, summarise


def test_summarise_keeps_the_lowest_and_highest_sample_across_channels() -> None:
    block = np.array([[0.1, -0.4], [0.7, 0.2], [-0.2, 0.0]], dtype=np.float32)

    column = summarise(block)

    assert column.low == np.float32(-0.4)
    assert column.high == np.float32(0.7)


def test_summarise_of_nothing_is_silence() -> None:
    assert summarise(np.zeros((0, 2), dtype=np.float32)) == SILENT_COLUMN


def test_a_chunk_is_split_into_evenly_timed_columns_ending_on_arrival() -> None:
    chunk = np.zeros((1024, 2), dtype=np.float32)
    chunk[700, 0] = 0.9

    columns = split_columns(chunk, 512, arrived=10.0, rate=48000)

    assert [column.at for column in columns] == pytest.approx([10.0 - 512 / 48000, 10.0])
    assert columns[1].high == pytest.approx(0.9)
    assert columns[0].peak == 0.0


def test_a_short_chunk_still_makes_one_column() -> None:
    assert len(split_columns(np.zeros((100, 2), dtype=np.float32), 512, 1.0, 48000)) == 1


def test_display_edges_are_linear_and_held_at_full_scale() -> None:
    assert WaveColumn(-1.4, 0.02).display == pytest.approx((-1.0, 0.02))


def test_peak_is_the_larger_excursion_either_side_of_zero() -> None:
    assert WaveColumn(-0.9, 0.3).peak == 0.9
    assert WaveColumn(-0.1, 0.6).peak == 0.6
