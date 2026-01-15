# Autonomous Dev Team

An AI-powered autonomous development system that tests applications, finds bugs, and fixes them automatically using Claude.

## Components

### Test Agents (Testers)
Simulated user personas that test your application and report issues:
- **Grandma Rose** - Elderly, non-tech-savvy viewer
- **Teen Nephew** - Impatient, tech-savvy teenager
- **Uncle Dave** - Detail-oriented curator
- **Security Auditor** - Security researcher looking for vulnerabilities

Each agent uses Claude to authentically embody their persona and report issues from their unique perspective.

### Mastermind Agent
Autonomous bug fixer that:
- Monitors Discord for new issues
- Analyzes issues with Claude
- Creates fix strategies
- Implements fixes via Git/Code workers
- Runs tests and creates PRs
- Auto-fixes CI failures (Black, flake8)
- Learns from past mistakes

### Discord Integration
- Issues reported to #bugs channel
- Fix progress tracked in threads
- Commands for status and control (`!mm status`, `!mm pause`, etc.)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Required environment variables:
- `ANTHROPIC_API_KEY` - Claude API key
- `DISCORD_BOT_TOKEN` - Discord bot token
- `DISCORD_BUGS_CHANNEL_ID` - Channel ID for bug reports
- `DISCORD_DEVLOG_CHANNEL_ID` - Channel ID for dev logs
- `FAMILY_ARCHIVE_HOST` - Target app host (or your app)
- `GH_TOKEN` - GitHub token for PR creation

### 3. Configure target project

Edit `config.py` to point to your target application:
- `FAMILY_ARCHIVE_URL` - Base URL of app to test
- `TEST_USERS` - Test user credentials
- `GITHUB_REPO` - Target repository

## Running

### Run Test Agents

```bash
# Run all agents once
python run_testers.py

# Run continuously every 5 minutes
python run_testers.py --continuous --interval 5

# Run specific agent(s)
python run_testers.py --agent grandma
python run_testers.py --agent grandma teen security
```

### Run Mastermind (Bug Fixer)

```bash
python run_mastermind.py
```

Mastermind connects to Discord and waits for issues in the #bugs channel.

### Discord Commands

| Command | Description |
|---------|-------------|
| `!mm status` | Show agent state, queue, costs |
| `!mm sessions` | List active fix sessions |
| `!mm queue` | Show pending issues |
| `!mm pause` | Pause processing new issues |
| `!mm resume` | Resume processing |
| `!mm cancel <id>` | Cancel a session |
| `!mm retry <id>` | Retry failed session |
| `!mm pr <number>` | Show PR status |
| `!mm cost` | Show token usage and costs |
| `!mm commands` | Show all commands |

## Architecture

```
autonomous-dev-team/
├── agents/                 # Test persona agents
│   ├── grandma_rose.py    # Elderly user persona
│   ├── teen_nephew.py     # Teen user persona
│   ├── uncle_dave.py      # Curator persona
│   └── security_auditor.py # Security tester
├── mastermind/            # Bug fixer agent
│   ├── bot.py             # Discord bot with commands
│   ├── mastermind.py      # Core coordinator
│   ├── session.py         # Fix session tracking
│   └── issue_parser.py    # Parse Discord embeds
├── workers/               # Task executors
│   ├── git_worker.py      # Git operations
│   ├── code_worker.py     # Code editing with Claude
│   ├── test_worker.py     # Test running
│   ├── docker_worker.py   # Docker operations
│   └── pr_monitor_worker.py # CI monitoring
├── safety/                # Safety mechanisms
│   ├── cost_tracker.py    # Budget management
│   ├── rate_limiter.py    # Rate limiting
│   └── learning_tracker.py # Self-improvement from failures
├── base_agent.py          # Base agent class (Claude-powered)
├── orchestrator.py        # Test orchestration
├── config.py              # App configuration
├── discord_utils.py       # Discord webhook helpers
├── run_testers.py         # Tester scheduler
└── run_mastermind.py      # Mastermind entry point
```

## User Personas

### Grandma Rose (Viewer)
- **Focus:** Finding videos of grandkids, simple navigation
- **Pain tolerance:** Low - gives up if confused
- **Voice:** "My eyesight isn't what it used to be..."

### Teen Nephew (Viewer)
- **Focus:** Speed, mobile-friendliness, modern UI, dark mode
- **Pain tolerance:** Very low - expects instant everything
- **Voice:** "Bruh, this is giving 2010 vibes ngl"

### Uncle Dave (Curator)
- **Focus:** Labeling workflow, batch operations, data accuracy
- **Pain tolerance:** Medium - works around issues but complains

### Security Auditor (Viewer)
- **Focus:** Authorization bypass, XSS, injection, info disclosure
- **Approach:** Intentionally tries to break things

## Creating Custom Agents

```python
from base_agent import BaseUserAgent, Issue

class MyPersonaAgent(BaseUserAgent):
    def __init__(self):
        super().__init__(
            name="My Persona",
            email="test@example.com",
            password="password",
            role="viewer",
            persona_description="Detailed description of this persona"
        )

    def get_test_scenarios(self):
        return [
            {"name": "scenario_name", "description": "What to test"},
        ]

    def run_scenario(self, scenario):
        issues = []

        # Load a page
        status, html, load_time = self.load_page("/some-page")

        # Use Claude to evaluate the experience as your persona
        context = f"I loaded a page in {load_time}s. Here's what I see: {html[:500]}"
        issue = self.evaluate_experience(context)
        if issue:
            issues.append(issue)

        # Brainstorm improvements
        suggestions = self.brainstorm_improvements("Page context here")
        issues.extend(suggestions)

        return issues
```

## How It Works

1. **Testers run** every 5 minutes (or on demand)
2. **Each persona** logs in and runs their test scenarios
3. **Claude powers** their reasoning - they think and respond as their character
4. **Issues are reported** to Discord #bugs channel
5. **Mastermind monitors** Discord for new issues
6. **When an issue appears**, Mastermind:
   - Creates a thread for the fix
   - Analyzes the issue with Claude
   - Creates a fix strategy
   - Implements the fix
   - Runs tests
   - Creates a PR
   - Monitors CI and fixes failures
7. **Learning system** tracks failures and improves over time

## License

MIT