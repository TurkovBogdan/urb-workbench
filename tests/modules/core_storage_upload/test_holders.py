"""The holders' registry: a consumer says how its codes take an upload, by the code's prefix."""

from __future__ import annotations

import pytest

from src.modules.core_storage_upload.dto import UploadHolder
from src.modules.core_storage_upload.errors import UnknownHolder
from src.modules.core_storage_upload.services import holders
from src.modules.core_storage_upload.services.holders import register_upload_holder, upload_holder

pytestmark = pytest.mark.pure


def _holder() -> UploadHolder:
    async def check(bare, *, title, description, workspace=None):
        return None

    async def attach(bare, spooled, *, filename, title, description, workspace=None):
        raise AssertionError

    async def answer(bare, attached):
        return {}

    return UploadHolder(check=check, attach=attach, answer=answer)


def test_a_code_is_read_by_its_prefix_in_any_case_and_its_bare_code_upper(holder):
    registered = _holder()
    register_upload_holder("note", registered)

    assert upload_holder(" note@ab12cd34ef ") == (registered, "AB12CD34EF")
    assert upload_holder("NOTE@ab12cd34ef")[0] is registered


@pytest.mark.parametrize("prefix", ["", "  ", "TASK@", "a@b"])
def test_a_prefix_is_one_word_before_the_at_sign(prefix):
    with pytest.raises(ValueError):
        register_upload_holder(prefix, _holder())


@pytest.mark.parametrize("code", ["NOPE@1", "TEST@", "TEST", "", "@1"])
def test_a_code_no_holder_reads_is_refused_naming_the_prefixes_there_are(holder, code):
    register_upload_holder("NOTE", _holder())

    with pytest.raises(UnknownHolder) as refused:
        upload_holder(code)

    assert "TEST@ / NOTE@" in str(refused.value)
    assert refused.value.holder == code


def test_a_second_registration_of_a_prefix_replaces_the_first(holder):
    first, second = _holder(), _holder()
    register_upload_holder("NOTE", first)
    register_upload_holder("note", second)

    assert upload_holder("NOTE@1")[0] is second
    assert list(holders._holders) == ["TEST", "NOTE"]
