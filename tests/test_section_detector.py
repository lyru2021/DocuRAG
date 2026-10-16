"""基于规则的论文章节标题检测测试。"""

from app.services.document_parser import ParsedPage
from app.services.section_detector import detect_sections


def make_page(text: str, page_number: int = 1):
    return ParsedPage(
        page_number=page_number,
        text=text,
        start_char=0,
        end_char=len(text),
    )


def test_detect_numbered_headings():
    text = (
        "1 Introduction\n"
        "Some research background.\n"
        "2 Methods\n"
        "Experimental details.\n"
    )

    results = detect_sections(text, [make_page(text)])

    assert [r.heading for r in results] == [
        "1 Introduction",
        "2 Methods",
    ]

    assert all(r.verification_status == "candidate" for r in results)


def test_detect_common_headings():
    text = (
        "Abstract\n"
        "This paper describes an experiment.\n"
        "Conclusion\n"
        "The method is effective.\n"
    )

    results = detect_sections(text, [make_page(text)])

    assert [r.heading for r in results] == [
        "Abstract",
        "Conclusion",
    ]


def test_no_heading():
    text = "This document contains ordinary sentences."

    results = detect_sections(text, [make_page(text)])

    assert results == []


def test_correct_character_offsets():
    text = "Some text.\n\n3 Results and Discussion\nDetails."

    results = detect_sections(text, [make_page(text)])

    assert len(results) == 1

    result = results[0]

    assert text[result.start_char:].startswith(
        "3 Results and Discussion"
    )


def test_missing_page_mapping_does_not_invent_page():
    text = "1 Introduction\nSome text."

    results = detect_sections(text, [])

    assert results == []


