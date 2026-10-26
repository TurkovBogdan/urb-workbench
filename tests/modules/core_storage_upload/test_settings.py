"""The module settings: the defaults before the store arrives, the store read at the moment of use,
and the schema's defaults as decided (JOURNAL@3D507AEB17 in TASK@774E2622B9)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.modules.core_storage_upload import settings

from .conftest import UploadSettings

pytestmark = pytest.mark.pure


def test_defaults_apply_before_the_settings_arrive():
    assert settings.request_ttl() == timedelta(minutes=15)
    assert settings.server_path_enabled() is True


def test_the_current_settings_store_is_read_at_use():
    settings.set_current(UploadSettings(request_ttl_minutes=3, server_path_enabled=False))

    assert settings.request_ttl() == timedelta(minutes=3)
    assert settings.server_path_enabled() is False


def test_the_schema_defaults_and_bounds_match_the_decisions():
    fields = {field.key: field for field in settings.SETTINGS_SCHEMA}

    assert {key: field.default() for key, field in fields.items()} == {
        "request_ttl_minutes": 15,
        "server_path_enabled": True,
    }
    assert (fields["request_ttl_minutes"].min, fields["request_ttl_minutes"].max) == (1, 1440)


@pytest.mark.parametrize("value", [0, 1441, True])
def test_a_lifetime_out_of_bounds_is_refused_by_the_schema(value):
    field = next(f for f in settings.SETTINGS_SCHEMA if f.key == "request_ttl_minutes")

    with pytest.raises(ValueError):
        field.validate(value)


def test_there_is_no_ceiling_of_the_upload_s_own():
    """One ceiling, the storage's: two would have to be kept in step by the person."""
    assert not any("size" in field.key for field in settings.SETTINGS_SCHEMA)
