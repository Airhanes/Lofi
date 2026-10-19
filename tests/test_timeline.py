import pytest

from lofi import timeline


def test_mix_duration_subtracts_one_crossfade_per_join():
    assert timeline.mix_duration([180, 200, 150], 4) == 530 - 8
    assert timeline.mix_duration([180], 4) == 180
    assert timeline.mix_duration([], 4) == 0


def test_track_starts_overlap_by_crossfade():
    assert timeline.track_starts([60, 62.5, 61], 4) == [0, 56, 114.5]
    assert timeline.track_starts([60, 60], 0) == [0, 60]


def test_last_track_ends_at_mix_end():
    durs = [181.3, 203.9, 149.2, 222.0]
    starts = timeline.track_starts(durs, 4)
    assert starts[-1] + durs[-1] == pytest.approx(timeline.mix_duration(durs, 4))


def test_timestamps_records():
    tracks = [{"title": "a", "file": "a.flac", "hash": "h1", "duration": 60},
              {"title": "b", "file": "b.flac", "hash": "h2", "duration": 70}]
    stamps = timeline.timestamps(tracks, 4)
    assert [s["start"] for s in stamps] == [0, 56]
    assert [s["index"] for s in stamps] == [1, 2]
    assert stamps[1]["hash"] == "h2"


def test_crossfade_longer_than_track_is_rejected():
    with pytest.raises(ValueError):
        timeline.timestamps([{"title": "a", "duration": 60}, {"title": "b", "duration": 6},
                             {"title": "c", "duration": 60}], 4)


@pytest.mark.parametrize("seconds,hours,expected", [
    (0, False, "0:00"), (59.99, False, "0:59"), (61, False, "1:01"), (3599, False, "59:59"),
    (3600, False, "1:00:00"), (65, True, "0:01:05"), (3725.7, True, "1:02:05"),
])
def test_fmt_ts(seconds, hours, expected):
    assert timeline.fmt_ts(seconds, hours) == expected


def test_parse_ts_roundtrip():
    for s in (0, 59, 61, 3599, 3600, 3725):
        assert timeline.parse_ts(timeline.fmt_ts(s)) == s
