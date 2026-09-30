"""Image preparation before reading.

The point is narrow: make what is already in the pixels easier to read. Nothing here recovers
information that is not there, and nothing here touches the original file. Every variant is a
derived artefact, produced in memory from a copy, and the original bytes and their hash are exactly
what they were before.

Built on Pillow and numpy, which the image is already carrying. OpenCV would add roughly 60MB and a
version-sensitive wheel to the container for operations that are a dozen lines here -- the same
judgement the project applies elsewhere about infrastructure added for its own sake.

The quality report is recorded rather than acted on. It says how legible the source is, which a
reviewer should see next to whatever was read from it; it does not decide anything by itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

PREPROCESSING_VERSION = "preprocess-v1"

# Laplacian variance below this reads as soft focus. Calibrated on the synthetic benchmark: a clean
# 1080x2400 screenshot sits far above it, the same image under a 3-pixel blur far below.
BLUR_VARIANCE_FLOOR = 120.0
# Standard deviation of luminance. A washed-out scan sits under this.
LOW_CONTRAST_FLOOR = 38.0
# Below this a phone screenshot has been downscaled so hard that small text is gone.
SMALL_IMAGE_PIXELS = 640 * 640
# A page tilted by less than this reads fine; rotating it would cost resampling for nothing.
SKEW_DEGREES_FLOOR = 1.0


@dataclass
class QualityReport:
    """What the image is like to read, in numbers a reviewer can check."""

    width: int
    height: int
    blur_variance: float
    contrast: float
    mean_luminance: float
    skew_degrees: float = 0.0
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "blur_variance": round(self.blur_variance, 2),
            "contrast": round(self.contrast, 2),
            "mean_luminance": round(self.mean_luminance, 2),
            "skew_degrees": round(self.skew_degrees, 2),
            "flags": self.flags,
            "preprocessing_version": PREPROCESSING_VERSION,
        }


def _luminance(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float64)


def _laplacian_variance(grey: np.ndarray) -> float:
    """Focus measure: how much high-frequency detail survives in the image.

    A sharp edge produces a large second derivative; blurring flattens it. The variance of the
    Laplacian over the whole frame is the standard single-number stand-in for focus.
    """
    if grey.size == 0:
        return 0.0
    kernel = np.array([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])
    padded = np.pad(grey, 1, mode="edge")
    response = sum(
        kernel[y, x] * padded[y : y + grey.shape[0], x : x + grey.shape[1]]
        for y in range(3)
        for x in range(3)
        if kernel[y, x]
    )
    return float(np.var(response))


def assess(image: Image.Image) -> QualityReport:
    """Measure legibility. Reported to the reviewer; never used to discard a source.

    Skew is measured here rather than only inside `variants`. A tilted page is perfectly sharp and
    perfectly contrasted, so it raises no other flag -- and a report that carried no skew flag meant
    the deskew step was never reached at all.
    """
    grey = _luminance(image)
    report = QualityReport(
        width=image.width,
        height=image.height,
        blur_variance=_laplacian_variance(grey),
        contrast=float(np.std(grey)) if grey.size else 0.0,
        mean_luminance=float(np.mean(grey)) if grey.size else 0.0,
        skew_degrees=_deskew_angle(grey),
    )
    if abs(report.skew_degrees) >= SKEW_DEGREES_FLOOR:
        report.flags.append("skewed")
    if report.blur_variance < BLUR_VARIANCE_FLOOR:
        report.flags.append("soft_focus")
    if report.contrast < LOW_CONTRAST_FLOOR:
        report.flags.append("low_contrast")
    if image.width * image.height < SMALL_IMAGE_PIXELS:
        report.flags.append("low_resolution")
    if report.mean_luminance < 70:
        report.flags.append("dark")
    return report


def _otsu_threshold(grey: np.ndarray) -> float:
    """The luminance that best separates ink from paper, chosen by Otsu's method."""
    histogram, _ = np.histogram(grey, bins=256, range=(0, 256))
    total = histogram.sum()
    if total == 0:
        return 128.0
    weights = np.cumsum(histogram)
    means = np.cumsum(histogram * np.arange(256))
    global_mean = means[-1] / total
    with np.errstate(divide="ignore", invalid="ignore"):
        background = np.where(weights > 0, means / np.maximum(weights, 1), 0.0)
        foreground = np.where(
            total - weights > 0, (means[-1] - means) / np.maximum(total - weights, 1), 0.0
        )
        between = weights * (total - weights) * (background - foreground) ** 2
    return float(np.argmax(np.nan_to_num(between))) or global_mean


# A rotation has to improve the row profile by at least this much before it is believed. Without
# the requirement, a washed-out page and an inverted one both "detected" a tilt of exactly the
# search limit -- the score drifted upward with angle and the search simply ran to the boundary.
SKEW_IMPROVEMENT_RATIO = 1.08


def _deskew_angle(grey: np.ndarray, *, limit: float = 8.0, step: float = 0.5) -> float:
    """The rotation that would make text lines horizontal, or zero when none clearly would.

    Found by projection profile: rotate a downscaled copy through small angles and keep the one
    whose row-sum profile varies most, because straight lines of text produce sharp peaks and
    troughs while skewed ones smear into each other.

    Returns the *correcting* rotation, so a page tilted by -4 degrees reports +4.

    Two guards stop it inventing a tilt. The winning angle must beat the profile at zero by a clear
    margin, and an answer sitting on the edge of the search range is discarded -- that is the shape
    of a score that never peaked, not of a page that happens to be tilted by exactly the limit.
    """
    if grey.size == 0:
        return 0.0
    # Binarised first: the profile should be driven by where the ink is, not by a gradient across
    # the page, which is what let a low-contrast image score higher the further it was rotated.
    threshold = _otsu_threshold(grey)
    ink = ((grey < threshold) * 255).astype(np.uint8)
    small = Image.fromarray(ink).resize((max(grey.shape[1] // 4, 32), max(grey.shape[0] // 4, 32)))

    def profile_score(angle: float) -> float:
        rotated = np.asarray(small.rotate(angle, resample=Image.BILINEAR, fillcolor=0), dtype=np.float64)
        return float(np.var(rotated.sum(axis=1)))

    baseline = profile_score(0.0)
    best_angle, best_score = 0.0, baseline
    angle = -limit
    while angle <= limit:
        score = profile_score(angle)
        if score > best_score:
            best_angle, best_score = angle, score
        angle += step

    if abs(best_angle) >= limit:
        return 0.0
    if baseline > 0 and best_score < baseline * SKEW_IMPROVEMENT_RATIO:
        return 0.0
    return best_angle


def variants(image: Image.Image, report: QualityReport | None = None) -> dict[str, Image.Image]:
    """Derived readings of the same pixels, in memory. The original is never modified.

    Which variants exist depends on what is wrong with the image, so a clean screenshot is not put
    through processing it does not need.
    """
    report = report or assess(image)
    grey_image = ImageOps.grayscale(image)
    produced: dict[str, Image.Image] = {"grayscale": grey_image}

    produced["autocontrast"] = ImageOps.autocontrast(grey_image, cutoff=1)

    if "soft_focus" in report.flags:
        # Unsharp masking cannot restore detail that blurring removed. It raises the edge contrast
        # of what survived, which is the difference between OCR finding a character boundary and
        # not finding one.
        produced["sharpened"] = produced["autocontrast"].filter(
            ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2)
        )

    if "low_resolution" in report.flags:
        produced["upscaled"] = produced["autocontrast"].resize(
            (image.width * 2, image.height * 2), resample=Image.LANCZOS
        )

    if "dark" in report.flags:
        produced["inverted"] = ImageOps.invert(produced["autocontrast"])

    grey = _luminance(produced["autocontrast"])
    threshold = _otsu_threshold(grey)
    produced["threshold"] = Image.fromarray(((grey > threshold) * 255).astype(np.uint8))

    angle = report.skew_degrees
    if abs(angle) >= SKEW_DEGREES_FLOOR:
        produced["deskewed"] = produced["autocontrast"].rotate(
            angle, resample=Image.BICUBIC, expand=True, fillcolor=255
        )

    return produced


def prepared_for_reading(image: Image.Image) -> tuple[Image.Image, QualityReport, list[str]]:
    """The single variant most likely to read well, with the report and the steps applied.

    Ordinary images come back essentially untouched: a clean screenshot needs no help, and putting
    one through thresholding loses the greys that anti-aliased text is made of.
    """
    report = assess(image)
    if not report.flags:
        return image, report, []

    produced = variants(image, report)
    for name in ("deskewed", "upscaled", "sharpened", "inverted", "autocontrast"):
        if name in produced:
            return produced[name], report, [name]
    return image, report, []
