# LogSentinel

AI-Powered Log Analyzer CLI

## Install

```bash
# From source
pip install -e .

# Or from PyPI (when published)
pip install logsentinel
```

## Usage

```bash
# Analyze log file
logsentinel /var/log/syslog

# Analyze docker container
logsentinel --container my-app

# JSON output
logsentinel app.log -o json

# Skip LLM analysis
logsentinel app.log --no-llm

# Multiple files
logsentinel app.log error.log

# Help
logsentinel --help
logsentinel --version
```

## Options

- `files` - Log files to analyze
- `-c, --container` - Docker container to analyze
- `-n, --lines` - Number of lines for docker logs (default: 100)
- `-o, --output` - Output format: text, json (default: text)
- `--no-llm` - Skip LLM analysis
- `-v, --verbose` - Verbose output
- `--version` - Show version

## Configuration

Set environment variables:
```bash
export OPENAI_API_KEY="your-key"
export LLM_PROVIDER="openai"  # or anthropic, groq, moonshot
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[all]"

# Run tests
pytest tests/ -v

# Build
python setup.py sdist bdist_wheel
```

## License

MIT
