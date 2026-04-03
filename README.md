# Auto-Assistance

AI-powered content automation system for content creation, curation, and multi-platform distribution.

## Features

- **Material Pool** - SQLite-based content storage for raw materials, refined atoms, and products
- **Content Dispatcher** - Automated pipeline: crawl → refine → rewrite → dispatch
- **Multi-Platform Support** - Weibo, Xiaohongshu (Little Red Book), Douyin, WeChat Public Account
- **Scheduled Execution** - Windows Task Scheduler integration for automated workflows

## Quick Start

### Prerequisites

- Python 3.10+
- Windows (for scheduled tasks)

### Installation

```bash
# Clone the repository
git clone https://github.com/jeremyko11/auto-assistance.git
cd auto-assistance

# Install dependencies
pip install -r requirements.txt
```

### Usage

```bash
# Interactive menu
python dispatcher/cli.py

# Command line modes
python dispatcher/content_dispatcher.py --mode full --skip-crawl
python dispatcher/content_dispatcher.py --status
python dispatcher/content_dispatcher.py --mode refine
python dispatcher/content_dispatcher.py --mode rewrite --platforms 微博 小红书
```

### Configuration

Edit `dispatcher/content_dispatcher.py` to configure:

- LLM API credentials (Xunfei Mars API)
- Platform cookies for posting
- Batch sizes and intervals

## Project Structure

```
auto-assistance/
├── material_pool.py              # Core database module
├── dispatcher/
│   ├── content_dispatcher.py    # Main pipeline engine
│   ├── cli.py                  # Interactive menu
│   └── poster.py               # Platform posting integration
├── content_pool/               # Content storage
│   ├── materials.db           # SQLite database
│   ├── queue_*.json           # Pending publish queues
│   └── generated_content.txt  # Generated content log
└── setup_schedules.bat        # Windows Task Scheduler setup
```

## Workflow

```
[1] Crawl     → Fetch content from platforms (Douyin, Weibo, Toutiao)
[2] Refine    → LLM extraction of atoms (quotes, cases, cognition, actions)
[3] Rewrite   → Adapt content for different platforms
[4] Dispatch  → Queue for manual publishing or API auto-post
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Feel free to submit issues and pull requests.