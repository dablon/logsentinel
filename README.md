# LogSentinel - AI-Powered Log Analyzer

## Overview

LogSentinel is a production-ready CLI tool that analyzes logs from multiple sources using AI to detect anomalies and provide actionable insights.

## Features

- **Multi-Source Log Collection**: Files, Docker containers, syslog
- **Intelligent Analysis**: Pattern detection, severity classification
- **AI-Powered Insights**: LLM integration (OpenAI, Anthropic, Groq, Moonshot)
- **Real-Time Detection**: Error/warning pattern recognition
- **Actionable Recommendations**: Based on common issues
- **Multiple Output Formats**: Text and JSON

## Installation

### From Source

```bash
git clone https://github.com/dablon/logsentinel.git
cd logsentinel
pip install -r requirements.txt
chmod +x logsentinel.py
```

### Using Go

```bash
go install github.com/dablon/logsentinel@latest
```

### Docker

```bash
docker build -t logsentinel .
```

## Usage

### Basic Usage

```bash
# Analyze log file
python3 logsentinel.py /var/log/syslog

# Analyze docker container logs
python3 logsentinel.py --container my-app

# Output as JSON
python3 logsentinel.py /var/log/app.log -o json

# Skip LLM analysis (faster)
python3 logsentinel.py /var/log/app.log --no-llm
```

### Command Options

| Option | Description |
|--------|-------------|
| `files` | Log files to analyze |
| `-c, --container` | Docker container to analyze |
| `-n, --lines` | Number of lines from docker (default: 100) |
| `-o, --output` | Output format: text, json |
| `--no-llm` | Skip LLM analysis |
| `-v, --verbose` | Verbose output |

### Examples

```bash
# Analyze application logs
python3 logsentinel.py /var/log/myapp.log

# Analyze docker container
python3 logsentinel.py --container nginx

# Multiple files
python3 logsentinel.py app.log error.log

# JSON output for automation
python3 logsentinel.py app.log -o json > result.json
```

## Configuration

Edit `config.yaml` or use environment variables:

```bash
export OPENAI_API_KEY="your-key"
export LLM_PROVIDER="openai"  # or anthropic, groq, moonshot
```

## Supported LLM Providers

| Provider | Env Variable | Model Default |
|----------|---------------|---------------|
| OpenAI | OPENAI_API_KEY | gpt-4o-mini |
| Anthropic | ANTHROPIC_API_KEY | claude-3-haiku |
| Groq | GROQ_API_KEY | llama-3.1-70b |
| Moonshot | MOONSHOT_API_KEY | moonshot-v1-8k |

## Output Example

```
=== LogSentinel Analysis ===

📊 Summary:
   Total: 150
   Errors: 12
   Warnings: 8

🔴 Top Errors:
   [ERROR] Database connection timeout
   [ERROR] Failed to authenticate user
   [CRITICAL] Out of memory

🟡 Top Warnings:
   [WARNING] High CPU usage detected
   [WARNING] Rate limit approaching

💡 Recommendations:
   - Connection issues detected - check network/service availability
   - Memory issues detected - check resource limits

🤖 LLM Insights:
   Root cause analysis from AI...
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Unit tests
pytest tests/unit/ -v

# E2E tests
pytest tests/e2e/ -v

# With coverage
pytest tests/unit/ --cov=. --cov-report=term
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Sources   │────▶│   Parser     │────▶│   Analyzer  │
│ (File/Docker│     │              │     │             │
└─────────────┘     └──────────────┘     └─────────────┘
                                                 │
                    ┌──────────────┐             │
                    │     LLM      │◀────────────
                    │   Analyzer   │
                    └──────────────┘
                            │
                    ┌─────────────┐
                    │   Output    │
                    │ (Text/JSON) │
                    └─────────────┘
```

## Requirements

- Python 3.10+
- requests
- pyyaml

## License

MIT License

---

*Version 1.0*
*Author: Blade*
