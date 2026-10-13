import pytest

from app.services.text_chunker import split_text


def test_short_text():
    chunks = split_text("Hello World", 300, 50)

    assert len(chunks) == 1
    assert chunks[0].content == "Hello World"
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 11


def test_empty_text():
    assert split_text("", 300, 50) == []


def test_long_paragraph():
    text = "A" * 1000
    chunks = split_text(text, 300, 50)

    assert len(chunks) == 4
    assert [len(c.content) for c in chunks] == [
        300, 300, 300, 250
    ]


@pytest.mark.parametrize(
    "chunk_size,overlap",
    [
        (300, -1),
        (300, 300),
        (300, 301),
        (0, 0),
        (-10, 0),
        (300, 1.5),
    ],
)
def test_invalid_parameters(chunk_size, overlap):
    with pytest.raises(ValueError):
        split_text("Hello", chunk_size, overlap)


def test_trailing_remainder():
    text = "B" * 620
    chunks = split_text(text, 300, 50)

    assert [(c.start_char, c.end_char) for c in chunks] == [
        (0, 300),
        (250, 550),
        (500, 620),
    ]


def test_content_matches_source_offsets():
    text = "第一段\n\n第二段\n测试文本" * 80
    chunks = split_text(text, 300, 50)

    assert len(chunks) > 1

    for index, chunk in enumerate(chunks):
        assert chunk.chunk_index == index
        assert chunk.content == text[
            chunk.start_char:chunk.end_char
        ]


def test_configs_300_and_500():
    text = "DocuRAG " * 200

    chunks_300 = split_text(text, 300, 50)
    chunks_500 = split_text(text, 500, 50)

    assert len(chunks_300) > len(chunks_500)

    for chunk in chunks_300:
        assert len(chunk.content) <= 300

    for chunk in chunks_500:
        assert len(chunk.content) <= 500
