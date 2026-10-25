# Usage Report

## Summary

The final solution is deterministic and makes **zero model calls**. It uses local Python parsing plus macOS Vision OCR for screenshots. No hosted model, no API key, and no paid inference service is used.

| Metric | Value |
|---|---:|
| Model providers | none |
| Model names | none |
| Model calls | **0** |
| Input tokens | **0** |
| Output tokens | **0** |
| Total tokens | **0** |
| Average tokens per request | **0.0** |
| Estimated total cost | **$0.00** |
| Estimated cost per request | **$0.000000** |
| Requests in final run | **518** |
| Full-run wall time (warm fact cache) | **43.57 s** |

## Per-model breakdown

No models were invoked, so there is no per-model breakdown.

| Provider | Model | Calls | Input tokens | Output tokens | Cost |
|---|---|---:|---:|---:|---:|
| — | — | 0 | 0 | 0 | $0.00 |
| **Overall** | — | **0** | **0** | **0** | **$0.00** |

## What runs locally

| Component | Work | Cost |
|---|---|---:|
| `code/evidence.py` | Parses 94 evidence files: logs, JSON, SQL, PDFs, TXT, screenshots | $0.00 |
| `code/ocr.swift` | Local macOS Vision OCR for 11 images, cached by SHA-256 | $0.00 |
| `code/state.py` | Identity matching, state reconstruction, account/analytics joins | $0.00 |
| `code/planner.py` / `code/serialize.py` | Policy application and deterministic CSV/JSON output | $0.00 |
| `code/evaluate.py` / `code/validate.py` / `tests/` | Local scoring, validation, and regression tests | $0.00 |

## Cost assumptions

- No external inference API is called.
- OCR runs on the local machine through the macOS Vision framework.
- The only costs are local CPU time and disk for the Python virtual environment and the OCR/fact caches.
- The reported $0.00 is therefore an actual inference cost, not an estimate based on a free-tier assumption.

## Reproducibility

```bash
python -m code.main --refresh
python -m code.main
python -m code.evaluate
python -m code.validate --output output.csv
python -m unittest discover -s tests -v
```

The `--refresh` run re-extracts facts and re-runs OCR only for images whose hash is not already in `.cache/ocr/`. The final 518-row run used the warm fact cache and completed in 43.57 seconds in the reference environment.
