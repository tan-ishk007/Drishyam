"""Image preparation, and the two things it must never do.

It must never claim a defect that is not there -- a false skew reading rotates a straight page and
loses sharpness for nothing. And it must never be kept when it reads worse than the untouched
image, because sharpening a legible page can thin strokes away.
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.evidence_intelligence import preprocessing as pp


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@pytest.fixture
def page() -> Image.Image:
    """A clean, straight, well-lit document page."""
    image = Image.new("RGB", (1080, 700), (250, 248, 244))
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(
        ["FIRST INFORMATION REPORT", "FIR No: 0142/2026", "Accused: Yash Kumar Gupta", "Vehicle MH12DE1433"]
    ):
        draw.text((70, 80 + index * 120), line, font=_font(52), fill=(20, 20, 20))
    return image


# --------------------------------------------------------------------------- assessment


def test_a_clean_page_raises_no_flags(page: Image.Image) -> None:
    assert pp.assess(page).flags == []


def test_a_blurred_page_is_recognised_as_soft(page: Image.Image) -> None:
    report = pp.assess(page.filter(ImageFilter.GaussianBlur(3.0)))
    assert "soft_focus" in report.flags
    assert report.blur_variance < pp.BLUR_VARIANCE_FLOOR


def test_a_washed_out_page_is_recognised_as_low_contrast(page: Image.Image) -> None:
    washed = Image.blend(page, Image.new("RGB", page.size, (200, 200, 200)), 0.80)
    assert "low_contrast" in pp.assess(washed).flags


def test_an_inverted_page_is_recognised_as_dark(page: Image.Image) -> None:
    assert "dark" in pp.assess(ImageOps.invert(page)).flags


def test_a_heavily_downscaled_page_is_recognised(page: Image.Image) -> None:
    assert "low_resolution" in pp.assess(page.resize((320, 208))).flags


# --------------------------------------------------------------------------- skew


@pytest.mark.parametrize("tilt", [-6.0, -4.0, 2.0, 5.0])
def test_a_tilted_page_reports_the_correcting_rotation(page: Image.Image, tilt: float) -> None:
    tilted = page.rotate(tilt, fillcolor=(250, 248, 244), resample=Image.BICUBIC)
    report = pp.assess(tilted)
    assert "skewed" in report.flags
    # The report gives the rotation that would put it straight, so it opposes the applied tilt.
    assert report.skew_degrees == pytest.approx(-tilt, abs=1.5)


@pytest.mark.parametrize(
    "degrade",
    [
        lambda image: image,
        lambda image: image.filter(ImageFilter.GaussianBlur(3.0)),
        lambda image: Image.blend(image, Image.new("RGB", image.size, (200, 200, 200)), 0.80),
        lambda image: ImageOps.invert(image),
        lambda image: image.resize((320, 208)),
    ],
)
def test_a_straight_page_is_never_reported_as_tilted(page: Image.Image, degrade) -> None:
    """A washed-out page and an inverted one both "detected" a tilt of exactly the search limit.

    The score drifted upward with angle and the search simply ran to the boundary, so a perfectly
    straight page was rotated by eight degrees before being read.
    """
    assert pp.assess(degrade(page)).skew_degrees == 0.0


# --------------------------------------------------------------------------- variants


def test_a_clean_page_is_passed_through_untouched(page: Image.Image) -> None:
    """Thresholding a clean page loses the greys that anti-aliased text is made of."""
    prepared, report, applied = pp.prepared_for_reading(page)
    assert applied == []
    assert prepared is page


@pytest.mark.parametrize(
    ("degrade", "expected"),
    [
        (lambda image: image.filter(ImageFilter.GaussianBlur(3.0)), "sharpened"),
        (lambda image: ImageOps.invert(image), "inverted"),
        (lambda image: image.resize((320, 208)), "upscaled"),
        (lambda image: image.rotate(-4, fillcolor=(250, 248, 244), resample=Image.BICUBIC), "deskewed"),
    ],
)
def test_a_degraded_page_gets_the_matching_preparation(page: Image.Image, degrade, expected: str) -> None:
    _, _, applied = pp.prepared_for_reading(degrade(page))
    assert applied == [expected]


def test_the_original_image_is_never_modified(page: Image.Image) -> None:
    """Every variant is derived. The bytes on disk and their hash stay exactly what they were."""
    before = page.tobytes()
    pp.variants(page)
    pp.prepared_for_reading(page)
    assert page.tobytes() == before


def test_the_report_is_serialisable_for_the_record(page: Image.Image) -> None:
    body = pp.assess(page.filter(ImageFilter.GaussianBlur(3.0))).to_dict()
    assert body["preprocessing_version"] == pp.PREPROCESSING_VERSION
    assert "soft_focus" in body["flags"]
    assert isinstance(body["blur_variance"], float)
    assert "skew_degrees" in body
