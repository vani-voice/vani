# Contributing to Vani

Thanks for your interest in Vani! We welcome contributions of all kinds — bug reports, feature requests, documentation improvements, and code.

## Getting Started

```bash
git clone https://github.com/vani-voice/vani
cd vani
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,sarvam]"
```

## Running Tests

```bash
# All 99 tests
make test

# Or directly
pytest tests/ -q
```

## Code Quality

```bash
make lint        # ruff linter
make typecheck   # mypy strict mode
make fmt         # auto-format with ruff
```

## Regenerating Protobuf Stubs

If you modify any `.proto` file under `proto/vani/v1/`:

```bash
make proto
```

This runs `grpc_tools.protoc` with the correct flags and output paths.

## Making Changes

1. **Open an issue first** — describe what you want to change and why
2. **Fork the repo** and create a branch from `main`
3. **Make your changes** — keep commits focused and well-described
4. **Run the tests** — `make test` must pass
5. **Open a pull request** — reference the issue number

All PRs require review before merging. The `main` branch is protected.

## What We're Looking For

We're actively looking for help in these areas:

### High Priority
- **Odia (`or-IN`) backend** — STT + TTS via Bhashini ULCA
- **Punjabi (`pa-IN`) backend** — STT + TTS via AI4Bharat or Bhashini
- **Santali (`sat-IN`) support** — any working STT pipeline

### Medium Priority
- Dialect-specific STT fine-tunes (Bhojpuri, Marwari, Rajasthani)
- More India Tool Registry entries (UPI, DigiLocker, CoWIN)
- Conformance test runner CLI tool
- gRPC server reference implementation

### Always Welcome
- Bug reports with reproduction steps
- Documentation improvements
- Performance benchmarks
- New examples and tutorials

## Project Structure

```
vani/
├── proto/vani/v1/       # Protobuf definitions (session, stream, action)
├── spec/                # Protocol spec documents (VAM-*.md)
├── vani/                # Python package
│   ├── backends/        # STT/LLM/TTS backend implementations
│   ├── gateway/         # Gateway pipeline (stub.py)
│   └── session.py       # Session config, codec negotiation
├── tests/               # pytest suite (99 tests)
├── conformance/         # YAML conformance test cases
├── demo/                # CLI mic demo
├── webapp/              # Browser-based web demo
└── examples/            # Example integrations
```

## Code Style

- Python 3.10+ (no walrus operators in hot paths for readability)
- Type hints everywhere — `mypy --strict` must pass
- Ruff for linting and formatting
- Docstrings on all public classes and functions

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).

---

Questions? Open a [Discussion](https://github.com/vani-voice/vani/discussions) or reach out via an issue.
