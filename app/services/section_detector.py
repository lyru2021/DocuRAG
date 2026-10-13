import re
from dataclasses import dataclass

from app.services.document_parser import ParsedPage
from app.services.page_mapper import find_chunk_page_range


@dataclass(frozen=True)
class SectionCandidate:
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
    candidates = []
    cursor = 0

    for line in text.splitlines(keepends=True): #保留换行符，防止偏移
        clean_line = line.strip()

        if clean_line:
            is_numbered = NUMBERED_HEADING.fullmatch(clean_line)   #要求整行符合标题形式
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
