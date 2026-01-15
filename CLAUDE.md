# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Autonomous Dev Team is a Claude-powered system that automatically tests applications, finds bugs, and fixes them. It consists of:

1. **Test Agents** - AI personas that test the app and report issues
2. **Mastermind** - Autonomous bug fixer that creates PRs
3. **Workers** - Git, code, test, and Docker operations
4. **Safety** - Cost tracking, rate limiting, learning from failures

## Common Commands

```bash
# Run test agents once
python run_testers.py

# Run test agents continuously
python run_testers.py --continuous --interval 5

# Run specific agent
python run_testers.py --agent grandma

# Start Mastermind (bug fixer)
python run_mastermind.py

# Test Discord connection
python test_discord.py
```

## Architecture

### Test Agents (`agents/`)
- Inherit from `BaseUserAgent` in `base_agent.py`
- Use `self.think()` for Claude-powered persona reasoning
- Use `self.evaluate_experience()` to find issues
- Use `self.brainstorm_improvements()` for feature suggestions

### Mastermind (`mastermind/`)
- `bot.py` - Discord bot with `!mm` commands
- `mastermind.py` - Core coordinator, fix strategy, Claude queries
- `session.py` - Fix session state tracking
- `issue_parser.py` - Parse Discord embed format

### Workers (`workers/`)
- `git_worker.py` - Branch creation, commits, PRs
- `code_worker.py` - File editing with Claude assistance
- `test_worker.py` - Run pytest, validate fixes
- `docker_worker.py` - Rebuild containers
- `pr_monitor_worker.py` - CI status monitoring, lint fixing

### Safety (`safety/`)
- `cost_tracker.py` - Track API costs, enforce budgets
- `rate_limiter.py` - Prevent API abuse
- `learning_tracker.py` - Learn from failures, inject lessons into prompts

## Key Patterns

### Agent Reasoning
Agents use Claude to think as their persona:
```python
response = self.think("What do I see on this page?")
```

### Issue Evaluation
```python
issue = self.evaluate_experience("Context about what happened")
if issue:
    self.report_issue(issue)
```

### Mastermind Query
```python
response = await self._query_claude(prompt, session, max_tokens=2000)
```

## Configuration

- `config.py` - App URL, Discord webhooks, test users
- `mastermind_config.py` - Claude model, cost limits, approval rules
- `.env` - API keys, tokens (not in repo)

## Discord Integration

Issues are reported via webhooks to #bugs channel. Mastermind bot uses:
- Bot token for real-time Discord connection
- Webhooks for one-way notifications

## Testing Target

Currently configured to test Family Archive app. To test a different app:
1. Update `FAMILY_ARCHIVE_URL` in config.py
2. Update `TEST_USERS` with valid credentials
3. Modify agent scenarios if needed
