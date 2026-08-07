# origo-info-adapter/tests/test_mapping.py
from __future__ import annotations

from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from origo_info_adapter.models import Band
from origo_info_adapter.stellarstation import mapping as m


def test_unset_timestamp_maps_to_none():
    assert m.to_dt(Timestamp()) is None  # epoch 0, not 1970-01-01


def test_set_timestamp_roundtrips():
    dt = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    assert m.to_dt(m.from_dt(dt)) == dt


def test_band_derivation():
    assert m.band_for_frequency(2_250_000_000) is Band.S_BAND
    assert m.band_for_frequency(8_200_000_000) is Band.X_BAND
    assert m.band_for_frequency(5_000_000_000) is Band.UNKNOWN
    assert m.band_for_frequency(None) is Band.UNKNOWN


def test_null_island_is_none_not_a_real_station():
    assert m._point(0.0, 0.0) is None
    assert m._point(78.2, 15.4) is not None


def test_reservation_token_never_in_model_dump():
    """The leak test — see models.py's ContactOption docstring."""
    from origo_info_adapter.models import ChannelSetInfo, ChannelSetRef, ContactOption

    option = ContactOption(
        channel_set=ChannelSetInfo(channel_set_ref=ChannelSetRef("cs-1")),
        reservation_token="super-secret-token",
    )
    assert "super-secret-token" not in repr(option)
    assert "reservation_token" not in option.model_dump()