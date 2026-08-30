"""Tests for the fetch_missing_medicine_images management command.

All Bing HTTP access is mocked. Only the DB query/filter and save paths are exercised.
"""

from __future__ import annotations

import json
import tempfile
from io import BytesIO
from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image

from apps.medicines.management.commands import fetch_missing_medicine_images as cmd
from apps.medicines.models import Medicine, PriceRegime


def _make_tiny_webp() -> bytes:
    """Return a valid WebP image large enough to pass the >1000 byte guard."""
    img = Image.new("RGB", (400, 400), (255, 0, 0))
    # Add noise so WebP can't compress it to nothing
    import random
    random.seed(42)
    pixels = img.load()
    for x in range(0, 400, 2):
        for y in range(0, 400, 2):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=90)
    return buf.getvalue()


def _bing_response_html(murl: str) -> str:
    """Minimal Bing Images HTML carrying one murl in an a.iusc element."""
    return (
        '<html><body>'
        '<a class="iusc" m=\'{"murl":"%s"}\'>'
        "</a></body></html>"
        % murl
    )


def _bing_empty_html() -> str:
    return "<html><body><p>no images</p></body></html>"


class BuildSearchQueryTests(TestCase):
    def test_query_includes_brand_and_optional_fields(self):
        med = Medicine(brand_name="Panadol", strength="500 mg", form="Tablet", manufacturer="GSK")
        self.assertEqual(cmd._build_search_query(med), "Panadol 500 mg Tablet GSK medicine")

    def test_query_with_only_brand(self):
        med = Medicine(brand_name="Abilify")
        self.assertEqual(cmd._build_search_query(med), "Abilify medicine")


class SearchBingImagesTests(TestCase):
    @mock.patch("apps.medicines.management.commands.fetch_missing_medicine_images.urlopen")
    def test_extracts_murl_from_iusc(self, mock_urlopen):
        url = "https://example.com/drug.webp"
        mock_urlopen.return_value.__enter__ = mock.Mock(return_value=mock.MagicMock(read=lambda: _bing_response_html(url).encode()))
        mock_urlopen.return_value.__exit__ = mock.Mock(return_value=False)
        results = cmd._search_bing_images("Panadol 500 mg medicine")
        self.assertEqual(results, [url])

    @mock.patch("apps.medicines.management.commands.fetch_missing_medicine_images.urlopen")
    def test_returns_empty_when_no_images(self, mock_urlopen):
        mock_urlopen.return_value.__enter__ = mock.Mock(return_value=mock.MagicMock(read=lambda: _bing_empty_html().encode()))
        mock_urlopen.return_value.__exit__ = mock.Mock(return_value=False)
        self.assertEqual(cmd._search_bing_images("xyzzy"), [])


class DownloadAndConvertTests(TestCase):
    @mock.patch("apps.medicines.management.commands.fetch_missing_medicine_images.urlopen")
    def test_converts_image_to_webp(self, mock_urlopen):
        fake_bytes = _make_tiny_webp()
        resp = mock.MagicMock()
        resp.read.return_value = fake_bytes
        resp.headers = {"Content-Type": "image/webp"}
        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=resp)
        ctx.__exit__ = mock.Mock(return_value=False)
        mock_urlopen.return_value = ctx

        result = cmd._download_and_convert("https://example.com/img.png")
        self.assertIsNotNone(result)
        data, ext = result
        self.assertEqual(ext, "webp")
        img = Image.open(BytesIO(data))
        self.assertEqual(img.size, (400, 400))


class FetchOneTests(TestCase):
    def setUp(self):
        self.med = Medicine.objects.create(brand_name="TestMed", form="Tablet", price_regime=PriceRegime.FREE)
        self.assertFalse(self.med.image)

    @mock.patch(
        "apps.medicines.management.commands.fetch_missing_medicine_images._search_bing_images",
        return_value=["https://example.com/real.webp"],
    )
    @mock.patch(
        "apps.medicines.management.commands.fetch_missing_medicine_images._download_and_convert",
        return_value=(_make_tiny_webp(), "webp"),
    )
    def test_saves_image_on_success(self, _dl_mock, _search_mock):
        result = cmd._fetch_one(self.med, delay=0)
        self.assertTrue(result)
        self.med.refresh_from_db()
        self.assertTrue(self.med.image.name.startswith("medicines/"))

    @mock.patch(
        "apps.medicines.management.commands.fetch_missing_medicine_images._search_bing_images",
        return_value=[],
    )
    def test_returns_false_when_no_urls(self, _search_mock):
        self.assertFalse(cmd._fetch_one(self.med, delay=0))
        self.med.refresh_from_db()
        self.assertTrue(self.med.image == "" or self.med.image is None)


class ManagementCommandTests(TestCase):
    def _run_cmd(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("fetch_missing_medicine_images", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_dry_run_lists_candidates(self):
        Medicine.objects.create(brand_name="AAA", price_regime=PriceRegime.FREE)
        Medicine.objects.create(brand_name="BBB", image="medicines/exists.webp", price_regime=PriceRegime.FREE)
        output = self._run_cmd("--dry-run")
        self.assertIn("AAA", output)
        self.assertNotIn("BBB", output)

    def test_limit_caps_candidates(self):
        for i in range(10):
            Medicine.objects.create(brand_name=f"Med{i:04d}", price_regime=PriceRegime.FREE)
        output = self._run_cmd("--dry-run", "--limit", "3")
        self.assertIn("Candidates: 3", output)

    @mock.patch(
        "apps.medicines.management.commands.fetch_missing_medicine_images._fetch_one",
        return_value=True,
    )
    def test_all_flag_processes_missing(self, mock_fetch):
        Medicine.objects.create(brand_name="OnlyThis", price_regime=PriceRegime.FREE)
        Medicine.objects.create(brand_name="Already", image="medicines/has.webp", price_regime=PriceRegime.FREE)
        self._run_cmd("--limit", "1")
        mock_fetch.assert_called_once()

    @mock.patch(
        "apps.medicines.management.commands.fetch_missing_medicine_images._fetch_one",
        return_value=False,
    )
    def test_abort_after_stops_on_streak(self, mock_fetch):
        for i in range(20):
            Medicine.objects.create(brand_name=f"Fail{i:04d}", price_regime=PriceRegime.FREE)
        output = self._run_cmd("--abort-after", "5")
        self.assertIn("Aborting", output)
        self.assertLess(mock_fetch.call_count, 20)
