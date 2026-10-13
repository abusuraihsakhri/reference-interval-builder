# Reference Interval Builder

A laboratory statistics utility for estimating two-sided reference intervals from an appropriately selected reference population. It provides a Python CLI and a standalone, browser-based calculator.

## Features

- Rank-based 2.5th and 97.5th percentile estimates using interpolation at rank `p × (n + 1)`.
- Approximate, binomial-rank confidence intervals for each reference limit (90% default).
- Optional Tukey 1.5 × IQR outlier exclusion with excluded counts.
- Per-group intervals and exploratory pairwise Harris–Boyd partition screening.
- CSV input, text/CSV reports, and warnings for fewer than 120 retained observations per group.
- Client-side CSV/pasted-data calculation and CSV download, without an application server.
- Separate, optional FastAPI audit/demo subsystem with an in-memory HMAC-linked audit trail.

**Clinical scope:** Estimates are research aids, **not automatically validated diagnostic reference limits**. The reference cohort, analyte, assay, partition choice, outlier decisions and interval suitability require laboratory review. The approximate rank CIs and simplified Harris–Boyd critical-value table are not substitutes for a complete CLSI EP28-A3c validation process. The generic audit/demo thresholds in `agents/` are not analyte-specific clinical reference limits.

## Browser application

Open `web/index.html` in a recent browser, or serve it locally:

```bash
python -m http.server 8080 --directory web
# Open http://localhost:8080
```

Upload a CSV (up to 5 MB and 50,000 rows), choose a numeric measurement column and optionally a group column, then calculate. Alternatively, paste an unpartitioned list of numeric measurements or load an example dataset. Choose a CI level, toggle Tukey screening, and export the table to CSV.

The browser calculates with JavaScript, matching the Python formulas in `refint/core.py`; it does **not** execute Python or load Pyodide. Files and pasted values remain in the browser and are not uploaded. There are no external runtime JavaScript dependencies.

The `.github/workflows/deploy-pages.yml` workflow publishes the `web/` directory when GitHub Pages is enabled with **GitHub Actions** as the source. A live URL should only be advertised after successful publication.

## Python installation and CLI

Requires Python 3.10 or later.

```bash
python -m pip install -r requirements.txt
python reference_interval_builder.py --input sample_data.csv --value-column glucose --group-column sex --ci 0.90
python reference_interval_builder.py --input sample_data.csv --value-column glucose --format csv --output report.csv
```

The reference-interval CLI accepts `--input`, `--value-column`, optional `--group-column`, `--ci` (finite, 0.5 through less than 1.0), `--format text|csv` and `--output`. Missing and non-finite CSV values are skipped; fewer than two valid observations per group cause an error. Reports include the total and retained sample sizes.

## Optional audit/demo API

This is a **separate** component and does not supply the statistical calculator UI. It uses mock responses, generic thresholds, and a process-local audit ledger.

```bash
export AUDIT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python cli.py audit --task-id TASK-001 --primary 28.5 --secondary 14.2
python cli.py verify-audit
python cli.py serve --host 127.0.0.1 --port 8000
# API: http://127.0.0.1:8000/docs
```

The API exposes `/health`, `/metrics`, `/api/audit`, `/api/chat`, and `/api/audit/logs`. Keep the server on a trusted local interface: it has no authentication, and its identifier guard is pattern-based screening, not comprehensive PHI de-identification. Audit entries are signed using `AUDIT_SECRET_KEY` and held in memory only; they are not durable across restarts. Provider names in `agents/llm_factory.py` currently resolve to a mock implementation, not real external LLM integrations.

For container use, `Dockerfile` and `docker-compose.yml` are supplied; configure a new signing secret in your local `.env` before starting. Never commit the secret or upload identifiable patient data to an untrusted service.

## Tests and technology

```bash
python -m pytest -q
python -m pip check
node --test web/app.test.cjs   # Node.js 22
```

Python uses NumPy, SciPy, Pydantic and FastAPI; the browser tool uses plain HTML, CSS and JavaScript. CI tests Python 3.10–3.12 and Node.js 22. The browser requires a modern JavaScript engine (ES2022-compatible). The project is licensed under [MIT](LICENSE).
