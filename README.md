# Reference Interval Builder

> **Domain:** Clinical Decision Support & Biomedical Computing
> **Reference Guidelines & Standards:** CLSI EP28-A3c, ISO/IEC Quality Frameworks

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)
![Audit Trail](https://img.shields.io/badge/Audit-HMAC--SHA256_Tamper--Evident-brightgreen.svg)
![Zero-PHI Guard](https://img.shields.io/badge/Guard-Zero--PHI_Outbound-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)

</div>

---

## 📖 What It Does

Reference Interval Builder computes clinical reference intervals from a sample of healthy-subject lab results using the CLSI EP28-A3c nonparametric percentile method, with Tukey outlier exclusion, rank-based confidence intervals, and the Harris-Boyd test for whether age/sex partitioning is statistically warranted.

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with sample data
python reference_interval_builder.py --input sample_data.csv \
    --value-column glucose --group-column sex --ci 0.90
```

---

## ⚙️ Key Capabilities & Algorithmic Modules

### Core Statistics (`refint/core.py`)

- **Tukey's Outlier Exclusion**: Flags and removes outliers using the 1.5 x IQR fence method before computing reference intervals.
- **CLSI EP28-A3c Nonparametric Percentile Method**: Computes the 2.5th and 97.5th percentile reference limits using rank-based interpolation.
- **Rank-Based Confidence Intervals**: Nonparametric confidence intervals around reference limits using the normal approximation to the binomial distribution.
- **Harris-Boyd Partitioning Test**: Determines whether two candidate subgroups (e.g., male/female) should be reported as separate reference intervals.

### CLI Interface (`reference_interval_builder.py`)

- **`read_csv_column()`**: Read a CSV file and return `{group_label: [values]}`.
- **`build_text_report()`**: Generate a human-readable text report.
- **`build_csv_report()`**: Generate a machine-readable CSV report.
- **`main()`**: CLI entry point with argument parsing.

### Enterprise Agent System (`agents/`)

- **Multi-Worker Evaluation**: InvariantQCWorker, SafetyEscalationWorker, ProtocolConformanceWorker.
- **Zero-PHI Outbound Interceptor**: AST and regex inspection blocking SSNs, MRNs, phone numbers, and patient identifiers.
- **HMAC-SHA256 Audit Trail**: Chained, cryptographically signed logs for every evaluation.
- **FastAPI REST Server**: OpenAPI 3.1 REST endpoints with Prometheus metrics.

---

## 💻 CLI Usage

### Reference Interval Builder (Core)

```bash
# Basic usage
python reference_interval_builder.py --input sample_data.csv \
    --value-column glucose --group-column sex --ci 0.90

# Output as CSV
python reference_interval_builder.py --input sample_data.csv \
    --value-column glucose --format csv --output report.csv

# Without grouping
python reference_interval_builder.py --input sample_data.csv \
    --value-column glucose --ci 0.95
```

### Parameters

| Parameter | Description | Default |
|:----------|:------------|:--------|
| `--input` | Path to CSV file of lab results | Required |
| `--value-column` | Name of the CSV column holding lab values | Required |
| `--group-column` | Optional CSV column (e.g., sex, age_group) for subgroup partitioning | None |
| `--ci` | Confidence level for reference limit CIs (0.5-1.0) | 0.90 |
| `--format` | Report output format (`text` or `csv`) | text |
| `--output` | Write report to file instead of stdout | None |

### Enterprise CLI (`cli.py`)

```bash
# Run audit
python cli.py audit --task-id TASK-001 --primary 28.5 --secondary 14.2

# Batch processing
python cli.py batch -i input.csv -o results.csv

# Verify audit trail
python cli.py verify-audit

# Launch API server
python cli.py serve --host 127.0.0.1 --port 8000
```

---

## 🛡️ Security Architecture

* **Zero-PHI Outbound Interceptor:** Active AST and regex inspection blocking SSNs, MRNs, phone numbers, and patient identifiers. Error messages do not leak regex patterns.
* **Tamper-Evident HMAC-SHA256 Audit Trail:** Chained, cryptographically signed logs for every evaluation. Requires `AUDIT_SECRET_KEY` environment variable.
* **Path Traversal Protection:** All user-supplied file paths are validated to prevent directory traversal attacks.
* **Input Validation:** CI levels, file paths, and data columns are validated before processing.

### Environment Variables

| Variable | Description | Required |
|:---------|:------------|:---------|
| `AUDIT_SECRET_KEY` | HMAC-SHA256 secret key for audit trail | Yes |
| `MODEL_PROVIDER` | LLM provider (mock, ollama, claude, openai) | No (default: mock) |

---

## 🧪 Testing

```bash
# Run all tests
pytest -v

# Run specific test files
pytest test_refint.py -v          # Core statistics tests
pytest test_security.py -v        # Security feature tests
pytest tests/ -v                  # Integration tests

# Run with coverage
pytest --cov=refint --cov=agents -v
```

---

## 🐳 Container Deployment

```bash
# Build and run with Docker
docker build -t reference-interval-builder .
docker run -e AUDIT_SECRET_KEY=your-secret-key -p 8000:8000 reference-interval-builder

# Or use docker-compose
cp .env.example .env
# Edit .env to set AUDIT_SECRET_KEY
docker-compose up -d
```

---

## 📁 Project Structure

```
reference-interval-builder/
├── refint/                    # Core statistics module
│   ├── __init__.py
│   └── core.py               # CLSI EP28-A3c implementation
├── agents/                    # Enterprise agent system
│   ├── __init__.py
│   ├── api.py                # FastAPI REST server
│   ├── base.py               # PHI guard, audit trail
│   ├── models.py             # Pydantic schemas
│   ├── supervisor.py         # Multi-worker orchestrator
│   ├── workers.py            # Specialized evaluation workers
│   ├── llm_factory.py        # LLM provider factory
│   ├── learning.py           # Bayesian calibration engine
│   ├── metrics.py            # Prometheus metrics
│   └── streamer.py           # WebSocket telemetry
├── tests/                     # Integration tests
│   ├── test_enrichment.py
│   └── test_reference_interval_builder.py
├── web/                       # Operations console
│   └── index.html
├── reference_interval_builder.py  # Core CLI entry point
├── cli.py                     # Enterprise CLI entry point
├── enrichment.py              # Enrichment feature engines
├── simulator.py               # High-throughput simulation
├── sample_data.csv            # Sample lab data
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container build
├── docker-compose.yml         # Container orchestration
├── .env.example               # Environment template
├── .gitignore                 # Git ignore rules
└── LICENSE                    # MIT License
```

---

## 📐 Mathematical Formulation

### Reference Interval (CLSI EP28-A3c)

```
Lower limit = 2.5th percentile (rank = 0.025 × (n + 1))
Upper limit = 97.5th percentile (rank = 0.975 × (n + 1))
```

### Tukey's Outlier Method

```
IQR = Q3 - Q1
Lower fence = Q1 - 1.5 × IQR
Upper fence = Q3 + 1.5 × IQR
Values outside fences are excluded
```

### Harris-Boyd Partitioning Test

```
z = |mean_a - mean_b| / sqrt(var_a/n_a + var_b/n_b)
Partition recommended if z > z_critical(n*)
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
