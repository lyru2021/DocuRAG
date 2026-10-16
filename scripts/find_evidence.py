"""从检索实验快照中定位真实术语及原文证据。"""

import argparse
import json
from pathlib import Path


def main() -> None:
    """搜索快照中的术语并输出可人工核对的候选证据。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path(
            "evaluation/snapshots/chunk300_overlap50.json"
        ),
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if not args.query.strip():
        parser.error("--query must not be empty")

    if args.limit < 1:
        parser.error("--limit must be positive")

    snapshot = json.loads(
        args.snapshot.read_text(encoding="utf-8")
    )

    matches = []
    seen = set()

    for paper in snapshot["papers"]:
        document_id = paper["document_id"]

        for chunk in paper["chunks"]:
            content = chunk["content"]
            search_text = content.casefold()
            term = args.query.casefold()

            position = 0

            while True:
                index = search_text.find(term, position)

                if index == -1:
                    break

                start_char = chunk["start_char"] + index
                end_char = start_char + len(args.query)

                key = (document_id, start_char, end_char)

                # 相邻 Chunk 重叠时避免重复报告同一处原文。
                if key not in seen:
                    seen.add(key)

                    matches.append({
                        "document_id": document_id,
                        "title": paper["title"],
                        "start_char": start_char,
                        "end_char": end_char,
                        "page_start": chunk["page_start"],
                        "page_end": chunk["page_end"],
                        "matched_text": content[
                            index:index + len(args.query)
                        ],
                        "context": content[
                            max(0, index - 100):
                            min(len(content), index + len(args.query) + 100)
                        ],
                    })

                position = index + 1

    matches.sort(
        key=lambda item: (
            item["document_id"],
            item["start_char"],
        )
    )

    print(
        json.dumps(
            {
                "query": args.query,
                "total_matches": len(matches),
                "matches": matches[:args.limit],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()