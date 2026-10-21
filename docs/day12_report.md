

# Day 12 — Multi-Step Research Agent Evaluation

## 1. Objective

Day 12 extends DocuRAG from single-step retrieval to a bounded, multi-step academic research workflow.

The system aims to retrieve evidence from multiple papers, identify missing evidence, perform one supplementary retrieval round when needed, verify source quotations, and generate an auditable research comparison report.

## 2. Implementation

The research workflow uses LangGraph and includes:

1. **Planning:** Identify document IDs and select initial retrieval queries.
2. **Retrieval:** Search real PostgreSQL paper chunks using registered tools.
3. **Field classification:** Identify candidate evidence related to methods, experimental conditions, and conclusions.
4. **Fact extraction:** Use DeepSeek to propose structured claims with quotes and source references.
5. **Quote verification:** Check document IDs, chunk IDs, page ranges, and exact substrings against retrieved evidence.
6. **Evidence coverage judging:** Identify research fields without verified quotations.
7. **Supplementary retrieval:** Allow at most one additional retrieval round, sharing the original tool-call budget.
8. **Evidence recheck:** Process newly retrieved chunks and recompute coverage.
9. **Final Evidence Matrix:** Consolidate verified quotations without automatically treating claims as semantically supported.
10. **Report rendering:** Produce an auditable Markdown report.

### Safety and resource limits

- Maximum 5 tool calls per research question.
- Maximum 1 supplementary retrieval round.
- PostgreSQL retrieval tools operate in short, read-only transactions.
- LLM-proposed references must match evidence retrieved in the current workflow.
- Invalid quotations are rejected.
- Individual tool or extraction failures should not erase previously retrieved evidence.

## 3. Real Evaluation Setup

### Documents

- **Document 31:** `A_Comparative_Study_of_Deep_Audio_Models_for_Spectrogram-_and_Waveform-Based_SingFake_Detection.pdf`
- **Document 32:** `A_Lightweight_Audio-Visual_Framework_for_Deepfake_Detection.pdf`

Both documents were reported as parsed in PostgreSQL.

### Environment

- Python 3.11.17
- PostgreSQL
- LangGraph
- DeepSeek through the OpenAI-compatible Responses API
- Configured model: `deepseek-flash`

### Evaluation questions

- Q1: Compare the detection methods used in the two papers.
- Q2: Compare the datasets and experimental conditions.
- Q3: Compare the reported evaluation metrics.
- Q4: Compare the main experimental findings.
- Q5: Compare the similarities and differences in deepfake detection.

## 4. Real Execution Results

| Question | Tool Calls | Supplement Rounds | Quotes Verified | Quotes Rejected | Total Tokens |
|---|---:|---:|---:|---:|---:|
| Q1 | 3 | 1 | 11 | 2 | 12,478 |
| Q2 | 3 | 1 | 9 | 0 | 8,132 |
| Q3 | 5 | 1 | 10 | 3 | 15,869 |
| Q4 | 5 | 1 | 12 | 3 | 14,876 |
| Q5 | 5 | 1 | 4 | 0 | 5,719 |
| **Total** | **21** | **5** | **46** | **8** | **57,074** |

All five executions finished without a top-level failure.

The exact quotation verification acceptance rate was **46/54 = 85.2%**.

This rate measures whether model-proposed quotations match the retrieved source records. It is **not** a measure of claim correctness, answer accuracy, or research reliability.

Token consumption covers reported LLM extraction usage. Actual monetary API costs were not measured in this evaluation.

## 5. Findings

### Successful capabilities

- The workflow retrieved records from two real PostgreSQL documents.
- The initial and supplementary retrieval steps respected the shared tool-call budget.
- Each evaluation used no more than one supplementary retrieval round.
- The system generated structured factual proposals with document IDs, chunk IDs, page ranges, and quotations.
- The backend rejected quotations that did not exactly match retrieved text.
- The final matrix retained verified quotations separately from semantically supported conclusions.

### Identified limitations

**PDF reading order**

Document 31 showed evidence of interleaved text likely caused by two-column PDF extraction. Some rejected quotations involved words from unrelated text inserted between portions of an otherwise plausible sentence. Original PDF pages require independent inspection before treating this diagnosis as confirmed.

**Task-specific evidence sufficiency**

The current Evidence Judge checks quotation coverage across three general fields: method, experimental conditions, and conclusion. It does not determine whether the evidence fully answers the user's particular research question.

**Evaluation-metric comparison**

Q3 completed execution but did not adequately establish a like-for-like comparison of the metrics and values reported by the two papers.

**Result attribution**

Some retrieved passages may describe related studies rather than the target paper's own experimental findings. Additional checks are needed to distinguish background literature from original experimental results.

**Semantic validation**

Exact quotation matching verifies text provenance, not whether an LLM-generated claim is supported by the cited passage. Independent semantic review remains necessary.

**Retrieval strategy**

The current planner uses a limited set of keyword rules. Some queries may miss important passages despite successful execution.

**Comparison generation**

The Markdown report currently presents source-grounded proposed facts and evidence gaps; it does not yet provide a fully validated synthesized comparison. The standalone report renderer is used separately from the Graph's conservative answer node.

## 6. Acceptance Status

| Requirement | Status |
|---|---|
| Multi-step research workflow | Implemented |
| Real PostgreSQL retrieval | Executed |
| DeepSeek structured fact extraction | Executed |
| Shared tool budget | Within limit in all five runs |
| One supplementary round maximum | Within limit in all five runs |
| Exact quote and source validation | Executed |
| Five real research questions | Executed |
| Fully verified semantic correctness | Not established |
| Complete task-specific answers | Not established |
| Reproducible local evaluation artifacts | Saved locally |

Overall conclusion: **Day 12's engineering workflow was implemented and exercised on real documents. Full research-answer quality validation remains open.**

## 7. Reproduction

Run the test suite:

```bash
python -m scripts.run_tests -q --tb=short
```

Run a single real research question:

```bash
python -m scripts.evaluate_day12_real --question 1
```

Run all five questions:

```bash
python -m scripts.evaluate_day12_real --all
```

Real evaluations require local PostgreSQL documents with the expected IDs and an appropriately configured DeepSeek API key.

The IDs 31 and 32 are specific to this evaluation database and are not portable identifiers.

## 8. Artifacts

A summary is stored at:

`evaluation/results/day12_real_summary.json`

Full execution states, original chunks, question reports, and human-review CSVs are retained locally and excluded from Git where configured.

Original experiment outputs are preserved as evidence of the measured results; rerunning the model may produce different outputs.

## 9. Follow-Up Priorities

1. Repair or improve PDF two-column reading-order extraction and revalidate affected chunks.
2. Add question-specific evidence requirements and retrieval planning.
3. Distinguish the target paper's original results from cited related work.
4. Complete human semantic audits and measure supported-claim rates.
5. Produce comparative conclusions only when supporting evidence is adequate.






