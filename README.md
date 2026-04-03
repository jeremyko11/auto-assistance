# Auto-Assistance

AI-powered content automation system for content creation, curation, and multi-platform distribution.

## Features

- **Material Pool** - SQLite-based content storage with quality scoring
- **Thinking Models** - Cross-disciplinary classification (Cognitive Bias, Compound Effect, Human Nature, etc.)
- **Emotional Resonance** - Content tagged with emotional triggers (Anxiety, Hope, Recognition, Surprise)
- **Content Dispatcher** - Automated pipeline: crawl → refine → rewrite → dispatch
- **Multi-Platform Support** - Weibo, Xiaohongshu, Douyin, WeChat Public Account
- **Quality Control** - Automatic quality scoring and routing

## Quick Start

```bash
cd auto-assistance

# Interactive menu
python dispatcher/cli.py

# Command line modes
python dispatcher/content_dispatcher.py --mode full --skip-crawl
python dispatcher/content_dispatcher.py --status
```

## Project Structure

```
auto-assistance/
├── material_pool.py              # Core database with quality scoring
├── dispatcher/
│   ├── content_dispatcher.py    # Main pipeline engine
│   ├── cli.py                  # Interactive menu
│   └── poster.py               # Platform posting integration
├── content_pool/               # Content storage
│   └── materials.db            # SQLite database
└── setup_schedules.bat        # Windows Task Scheduler
```

## Workflow

```
[1] Crawl     → Fetch content from platforms
[2] Refine    → LLM extraction with ThinkingModel + Emotional tags
[3] Rewrite   → Adapt for different platforms with professional prompts
[4] Dispatch  → Queue for publishing or auto-post
```

## Quality Scoring

Each atom is scored on:
- **Completeness** - Content depth and structure
- **Uniqueness** - Deduplication against existing content
- **IP Fit** - Alignment with IP direction keywords
- **Actionable** - Practical value for audience
- **Emotional** - Emotional resonance potential

## Thinking Models

Classification system from查理·芒格 methodology:
- Cognitive Bias (认知偏差)
- Compound Effect (复利效应)
- Human Nature (人性本质)
- Career Strategy (职场策略)
- Relationship Dynamics (关系动力学)
- Systems Thinking (系统思维)

## License

MIT License