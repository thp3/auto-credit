import pytest

from PySide6.QtGui import QRawFont

from auto_credit.artwork import end_card, font, overlay
from auto_credit.models import Credit


@pytest.mark.parametrize("url", ["", "javascript:alert(1)", "https://", "https://a.test/a b",
                                 "https://user:pass@a.test/", "https://a.test:bad/"])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        Credit("YouTube", "@author", url).validate()


def test_literal_text_and_cjk_layout():
    assert QRawFont.fromFont(font(24)).supportsCharacter("影"), "CJK font required for visual QA"
    credit = Credit("自訂平台", "@原作者 ' : % [id]", "https://example.com/原片?q=a&b=2")
    credit.validate()
    assert credit.overlay_text == "credit: @原作者 ' : % [id]"
    assert credit.url in credit.caption
    for width, height in [(1920, 1080), (1080, 1920), (640, 360), (360, 640)]:
        watermark = overlay(credit, width, height)
        assert watermark.pixelColor(0, 0).alpha() == 0
        assert any(watermark.pixelColor(x, y).alpha()
                   for x in range(width // 2, width, 4)
                   for y in range(height // 4))
        card = end_card(credit, width, height)
        assert (card.width(), card.height()) == (width, height)
        assert card.pixelColor(0, 0).alpha() == 255


def test_long_url_fits_portrait_and_landscape():
    credit = Credit("Instagram", "@" + "長名稱" * 30, "https://example.com/video?" + "a" * 600)
    credit.validate()
    for width, height in [(1280, 720), (720, 1280)]:
        assert not end_card(credit, width, height).isNull()


def test_qt_window_layout_and_preview(qt_app, tmp_path):
    from PySide6.QtCore import QSettings
    from auto_credit.app import Window
    window = Window(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    window.show()
    credit = Credit("YouTube", "@測試作者", "https://example.com/original")
    window.author.setText(credit.author)
    window.url.setText(credit.url)
    window.end_preview.set_image(end_card(credit, 1080, 1920))
    qt_app.processEvents()
    window.resize(960, 720)
    qt_app.processEvents()
    assert window.export_button.isVisible()
    assert window.end_preview.image.width() == 1080
    assert window.credit().author == credit.author
    window.close()
