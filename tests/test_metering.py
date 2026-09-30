import threading

import numpy as np
import pytest

from onemic.services.metering import BYTES_PER_COLUMN, ChannelMeter, Metering, TapReader, decode
from tests.fakes import FakeStream, FakeTaps


def chunk(*frames: tuple[float, float]) -> bytes:
    return np.array(frames, dtype=np.float32).tobytes()


def test_decode_shapes_samples_into_frames() -> None:
    samples = decode(chunk((0.1, -0.1), (0.5, 0.25)))

    assert samples.shape == (2, 2)
    assert samples[1, 0] == pytest.approx(0.5)


def test_decode_drops_a_partial_trailing_frame() -> None:
    assert decode(chunk((0.1, 0.2)) + b"\x00\x00\x00").shape == (1, 2)


def test_meter_keeps_recent_columns_and_holds_the_peak() -> None:
    now = [0.0]
    meter = ChannelMeter(history=2, clock=lambda: now[0])

    meter.push(decode(chunk((0.9, -0.2))))
    now[0] = 0.5
    meter.push(decode(chunk((0.1, -0.1))))
    meter.push(decode(chunk((0.2, 0.0))))

    reading = meter.reading()
    assert len(reading.columns) == 2
    assert reading.held_peak == pytest.approx(0.9)


def test_reader_feeds_the_meter_until_the_stream_ends() -> None:
    meter = ChannelMeter()
    stream = FakeStream([chunk((0.5, 0.5)) * (BYTES_PER_COLUMN // 8)] * 3)

    reader = TapReader(stream, meter)
    reader.close()

    assert len(meter.reading().columns) <= 3
    assert stream.closed


def test_sync_opens_wanted_taps_and_closes_unwanted_ones() -> None:
    taps = FakeTaps()
    metering = Metering(taps)

    metering.sync({"a": "tap.a", "mix": "tap.mix"})
    metering.sync({"mix": "tap.mix"})

    assert set(taps.opened) == {"tap.a", "tap.mix"}
    assert taps.opened["tap.a"].closed
    assert not taps.opened["tap.mix"].closed
    assert set(metering.readings()) == {"mix"}
    metering.close()
    assert taps.opened["tap.mix"].closed


def test_a_renamed_tap_is_reopened() -> None:
    taps = FakeTaps()
    metering = Metering(taps)

    metering.sync({"mix": "onemic.a.tap.mix"})
    metering.sync({"mix": "onemic.b.tap.mix"})

    assert taps.opened["onemic.a.tap.mix"].closed
    assert "onemic.b.tap.mix" in taps.opened
    metering.close()


def test_a_tap_that_cannot_start_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    metering = Metering(FakeTaps(failing={"tap.a"}))

    metering.sync({"a": "tap.a"})

    assert metering.readings() == {}
    assert "Meter for a unavailable" in caplog.text


def test_meter_is_safe_to_read_while_being_written() -> None:
    meter = ChannelMeter()
    block = decode(chunk((0.3, 0.3)))

    def write() -> None:
        for _ in range(2000):
            meter.push(block)

    writer = threading.Thread(target=write)

    writer.start()
    while writer.is_alive():
        meter.reading()
    writer.join()

    assert meter.reading().held_peak == pytest.approx(0.3)
