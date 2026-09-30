"""What the PDF font can draw, and what happens to everything else.

ReportLab's built-in fonts are Type-1 with WinAnsi encoding. A character outside that set is not
refused — it is written as raw UTF-8 bytes that the viewer reads back as Latin-1, so a downward
arrow reached the page as three garbage letters. Quoted OCR text can hold any character at all,
so every string the report prints is reduced to what the font can actually render.
"""

from __future__ import annotations

from app.services.reporting import _renderable, _safe


def test_plain_text_is_untouched():
    assert _renderable("Paid to Release Desk") == "Paid to Release Desk"


def test_characters_the_font_can_draw_are_kept():
    # These are all WinAnsi and render correctly today; substituting them would be a regression.
    assert _renderable("an em dash — a middle dot · a bullet • curly “quotes”") == (
        "an em dash — a middle dot · a bullet • curly “quotes”"
    )


def test_arrows_become_something_the_font_has():
    assert _renderable("RECEIVED → REVIEWED") == "RECEIVED > REVIEWED"
    assert _renderable("↓") == "v"


def test_the_rupee_sign_keeps_its_meaning():
    """A quote is the part a reviewer checks; turning its currency mark into "?" destroys it."""
    assert _renderable("Py Release Desk ₹12,000") == "Py Release Desk Rs12,000"


def test_an_undrawable_character_is_marked_not_dropped():
    # A screenshot can contain anything. Silently deleting it would misrepresent the source.
    assert _renderable("balance 😀 ok") == "balance ? ok"
    assert _renderable("中文") == "??"


def test_safe_still_escapes_markup_after_substitution():
    assert _safe("a → b & <c>") == "a &gt; b &amp; &lt;c&gt;"


def test_safe_keeps_zero_rather_than_blanking_it():
    assert _safe(0) == "0"
    assert _safe(None) == ""
