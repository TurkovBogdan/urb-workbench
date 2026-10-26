"""``/storage/{store}/{code}`` and ``…/download[/{name}]``: the bytes and their headers, the name
to save under, the cache tag, and one 404 for every way a file is not served.

The name is the address's: ``/download/<name>`` saves the file as ``name`` — with the file's
extension when the name has none; an opening, a download
without a name and a name the storage could not keep go out under the neutral ``<CODE><ext>``. The
route reads no holder, so no name kept in the storage goes out by itself.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from src.modules.core_storage.dto import Owner
from src.modules.core_storage.services.files import file_delete, file_path
from src.modules.core_storage.services.registration import file_register_bytes

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<html><body><script>alert(1)</script></body></html>"
OWNER = Owner(type="test", id="1")


async def _public(data: bytes = PNG, filename: str = "photo.PNG"):
    return await file_register_bytes(data, store="public", owner=OWNER, filename=filename)


def _disposition_name(response) -> str:
    return response.headers["content-disposition"].split('filename="', 1)[1].split('"', 1)[0]


async def test_a_public_file_comes_back_with_its_mime_and_headers(db, client):
    stored = await _public()

    response = await client.get(f"/storage/public/{stored.code}")

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"] == f'"{stored.sha256}"'
    assert response.headers["cache-control"] == "no-cache"
    assert "content-security-policy" not in response.headers
    assert response.headers["content-disposition"] == (
        f"inline; filename=\"{stored.code}.png\"; filename*=UTF-8''{stored.code}.png"
    )


async def test_the_code_is_taken_in_any_case(db, client):
    stored = await _public()

    response = await client.get(f"/storage/public/{stored.code.lower()}")

    assert response.status_code == 200
    assert response.content == PNG


async def test_download_asks_to_save_under_the_name_of_the_address(db, client):
    stored = await _public()

    response = await client.get(f"/storage/public/{stored.code}/download/test.json")

    assert response.status_code == 200
    assert response.content == PNG
    # The name says what to save the bytes as; their type stays the stored one.
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"test.json\"; filename*=UTF-8''test.json"
    )


async def test_a_name_without_an_extension_takes_the_files(db, client):
    """A holder's title carries no extension: saved as given, the file would open with nothing."""
    stored = await _public(b"# notes\n", "readme.md")
    title = "Чек-лист проверки"

    response = await client.get(f"/storage/public/{stored.code}/download/{quote(title, safe='')}")

    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith(
        "filename*=UTF-8''" + quote(f"{title}.md", safe="")
    )


async def test_download_without_a_name_saves_under_the_code(db, client):
    stored = await _public(filename="secret-plan.png")

    response = await client.get(f"/storage/public/{stored.code}/download")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(
        f'attachment; filename="{stored.code}.png"'
    )


async def test_the_name_kept_in_the_storage_never_goes_out_by_itself(db, client):
    """A name brought in one workspace is not the address's: opening and a bare download both
    give the neutral name, whatever the owners keep."""
    stored = await _public(filename="secret-plan.png")

    opened = await client.get(f"/storage/public/{stored.code}")
    saved = await client.get(f"/storage/public/{stored.code}/download")

    assert _disposition_name(opened) == f"{stored.code}.png"
    assert _disposition_name(saved) == f"{stored.code}.png"
    assert "secret-plan" not in opened.headers["content-disposition"]
    assert "secret-plan" not in saved.headers["content-disposition"]


async def test_the_old_query_names_nothing(db, client):
    """``?download=1`` and ``?holder=`` are gone: an opening stays an opening under the code."""
    stored = await _public()

    response = await client.get(
        f"/storage/public/{stored.code}", params={"download": "1", "holder": "TEST@1"}
    )

    assert response.headers["content-disposition"].startswith(
        f'inline; filename="{stored.code}.png"'
    )


@pytest.mark.parametrize(
    ("data", "filename", "mime"),
    [(SVG, "chart.svg", "image/svg+xml"), (HTML, "page.html", "text/html")],
)
async def test_a_document_that_can_run_script_is_sandboxed(db, client, data, filename, mime):
    stored = await _public(data, filename)

    for url in (f"/storage/public/{stored.code}", f"/storage/public/{stored.code}/download/x.txt"):
        response = await client.get(url)

        assert response.status_code == 200
        assert response.headers["content-type"].split(";")[0] == mime
        assert response.headers["content-security-policy"] == "sandbox"
        assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_cyrillic_name_goes_in_filename_star_with_an_ascii_fallback(db, client):
    name = "Отчёт за май.pdf"
    stored = await _public(b"%PDF-1.4\n" + b"0" * 32, "x.pdf")

    response = await client.get(
        f"/storage/public/{stored.code}/download/{quote(name, safe='')}"
    )

    header = response.headers["content-disposition"]
    assert header == (
        f"attachment; filename=\"{stored.code}.pdf\"; filename*=UTF-8''{quote(name, safe='')}"
    )
    assert header.isascii()


@pytest.mark.parametrize(
    "name",
    ["%01bad.png", "a" * 300 + ".png", "%20%20"],
    ids=["control-character", "too-long", "blank"],
)
async def test_a_name_the_storage_could_not_keep_saves_under_the_code(db, client, name):
    stored = await _public()

    response = await client.get(f"/storage/public/{stored.code}/download/{name}")

    assert response.status_code == 200
    assert _disposition_name(response) == f"{stored.code}.png"
    assert "filename*=UTF-8''" + f"{stored.code}.png" in response.headers["content-disposition"]


async def test_a_name_with_a_slash_is_no_address_of_a_file(db, client):
    """``/`` cannot be part of a name: the path has a segment too many and serves nothing."""
    stored = await _public()

    response = await client.get(f"/storage/public/{stored.code}/download/dir/x.png")

    assert response.status_code == 404


async def test_head_answers_the_headers_without_the_bytes(db, client):
    stored = await _public()

    for url in (f"/storage/public/{stored.code}", f"/storage/public/{stored.code}/download/a.png"):
        response = await client.head(url)

        assert response.status_code == 200
        assert response.content == b""
        assert response.headers["content-length"] == str(len(PNG))
        assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_matching_tag_gets_304_without_the_bytes(db, client):
    stored = await _public()

    response = await client.get(
        f"/storage/public/{stored.code}", headers={"If-None-Match": f'"{stored.sha256}"'}
    )

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == f'"{stored.sha256}"'


async def test_a_deleted_file_is_not_revalidated_from_the_cache(db, client):
    stored = await _public()
    await file_delete(stored.code)

    response = await client.get(
        f"/storage/public/{stored.code}", headers={"If-None-Match": f'"{stored.sha256}"'}
    )

    assert response.status_code == 404


async def _miss(client, url: str):
    response = await client.get(url)
    return response.status_code, response.json()


async def test_every_miss_is_one_answer(db, client):
    public = await _public()
    private = await file_register_bytes(b"secret", store="private", owner=OWNER, filename="s.txt")
    deleted = await _public(b"\x89PNG\r\n\x1a\n" + b"\x01" * 32, "gone.png")
    await file_delete(deleted.code)
    no_bytes = await _public(b"\x89PNG\r\n\x1a\n" + b"\x02" * 32, "lost.png")
    file_path(no_bytes).unlink()
    reference = await _miss(client, "/storage/public/0000000000")

    misses = [
        await _miss(client, f"/storage/private/{private.code}"),
        await _miss(client, f"/storage/private/{private.code}/download"),
        await _miss(client, f"/storage/private/{private.code}/download/s.txt"),
        await _miss(client, f"/storage/public/{private.code}"),
        await _miss(client, f"/storage/other/{public.code}"),
        await _miss(client, "/storage/public/not-a-code"),
        await _miss(client, "/storage/public/not-a-code/download/x.png"),
        await _miss(client, f"/storage/public/{deleted.code}"),
        await _miss(client, f"/storage/public/{deleted.code}/download/gone.png"),
        await _miss(client, f"/storage/public/{no_bytes.code}"),
    ]

    assert reference == (
        404,
        {"error": "File not found", "code": None, "params": None, "fields": None},
    )
    assert misses == [reference] * len(misses)
    # Positive control: the served one is still served.
    assert (await client.get(f"/storage/public/{public.code}")).status_code == 200


@pytest.mark.pure
def test_the_addresses_to_open_and_to_save_under_a_name():
    from src.modules.core_storage_view.services.links import public_download_path, public_file_path

    assert public_file_path(" ab12000001 ") == "/storage/public/AB12000001"
    assert public_download_path("ab12000001") == "/storage/public/AB12000001/download"
    assert public_download_path("AB12000001", "test.json") == (
        "/storage/public/AB12000001/download/test.json"
    )
    # A name of dots only would step out of the path in a browser: it goes as none.
    assert public_download_path("AB12000001", "..") == "/storage/public/AB12000001/download"
    assert public_download_path("AB12000001", ".") == "/storage/public/AB12000001/download"
    assert public_download_path("AB12000001", "Отчёт за май/v2.pdf") == (
        "/storage/public/AB12000001/download/"
        "%D0%9E%D1%82%D1%87%D1%91%D1%82%20%D0%B7%D0%B0%20%D0%BC%D0%B0%D0%B9%2Fv2.pdf"
    )
