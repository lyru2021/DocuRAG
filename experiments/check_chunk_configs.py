"""手动比较不同 chunk 配置的实验脚本。"""

from statistics import mean

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import Document
from app.services.text_chunker import split_text


CONFIGS = [
    (300, 50),
    (500, 50),
]


def main():
    """对已解析文档比较不同 chunk 配置产生的长度分布。"""

    with SessionLocal() as db:
        documents = db.scalars(
            select(Document)
            .where(Document.parse_status == "parsed")
            .order_by(Document.id)
        ).all()

        if not documents:
            print("No parsed documents found.")
            return

        for document in documents:
            text = document.extracted_text

            if not text:
                continue

            print(f"\nDocument ID: {document.id}")
            print(f"Filename: {document.filename}")
            print(f"Text length: {len(text)}")

            for chunk_size, overlap in CONFIGS:
                chunks = split_text(
                    text,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )

                lengths = [len(c.content) for c in chunks]

                print(
                    f"chunk_size={chunk_size}, "
                    f"overlap={overlap}, "
                    f"count={len(chunks)}, "
                    f"min={min(lengths) if lengths else 0}, "
                    f"max={max(lengths) if lengths else 0}, "
                    f"avg={mean(lengths) if lengths else 0:.2f}"
                )


if __name__ == "__main__":
    main()
