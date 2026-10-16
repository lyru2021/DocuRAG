"""基于规则的论文章节标题检测器。"""

import re
from dataclasses import dataclass

from app.services.document_parser import ParsedPage
from app.services.page_mapper import find_chunk_page_range


@dataclass(frozen=True)
class SectionCandidate:
    """规则检测出的论文章节候选。"""

    heading: str
    page_number: int
    start_char: int
    detection_method: str = "regex"
    verification_status: str = "candidate"


NUMBERED_HEADING = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)"
    r"(?P<title>[A-Za-z][A-Za-z0-9 ,:/()&-]{2,100})$"
)

COMMON_HEADING = re.compile(
    r"^(Abstract|Introduction|Related Work|"
    r"Methodology|Methods|Materials and Methods|"
    r"Experimental Setup|Experiments|Results|"
    r"Results and Discussion|Discussion|"
    r"Conclusion|Conclusions|References)$",
    flags=re.IGNORECASE,
)


def detect_sections(
    text: str,
    pages: list[ParsedPage],
) -> list[SectionCandidate]:
    """从论文全文中检测章节标题。

    Args:
        text: PDF 解析后合并的完整文本。
        pages: 每页文本在完整文本中的字符区间。

    Returns:
        list[SectionCandidate]: 按原文出现顺序返回的章节候选。

    Notes:
        当前检测策略偏保守，只识别英文编号标题和常见论文标题；
        页码来自字符区间映射，避免同名章节或重复文本造成误定位。
    """

    candidates = []
    cursor = 0

    for line in text.splitlines(keepends=True):
        # 保留换行符推进 cursor，防止标题 start_char 与原文发生偏移。
        clean_line = line.strip()

        if clean_line:
            # 要求整行符合标题形式，避免正文中包含类似片段时被误判为标题。
            is_numbered = NUMBERED_HEADING.fullmatch(clean_line)
            is_common = COMMON_HEADING.fullmatch(clean_line)

            if is_numbered or is_common:
                leading_spaces = len(line) - len(line.lstrip())
                start_char = cursor + leading_spaces

                page_start, _ = find_chunk_page_range(
                    start_char,
                    start_char + len(clean_line),
                    pages,
                )

                if page_start is not None:
                    candidates.append(
                        SectionCandidate(
                            heading=clean_line,
                            page_number=page_start,
                            start_char=start_char,
                        )
                    )

        cursor += len(line)

    return candidates
