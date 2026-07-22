# Listing2content Project
## Overview

This is a Saas product Created for luxury and resort real estate agents who wish to automate their listing in formation and create full content packages. It ingests new listing data (photos, real estatespecs and features, MLS details) and automatically drafts a full content package (carousel, caption set, Reel script) in the agent's voice and the resort-market lifestyle framing, ready for a quick approve/edit pass. The users can carry an AI chat in order to instruct how to input their listing data and to edit and save their packages. 
## Development Process

When instructed to build a feature:
1. Receive the feature request fromt the prompt 
1. Develop the feature - do not skip and step from the feature-dev 7 step process
1. Thoroughly test the feature with unit tests and integeration tests and fix any issues
1. Submit a PR using your github tools

## Ai Design

When writing code to make calls to LLMs, use your Cerebras skill to use LiteLLM via OpoenRouter to the openai/gpt-oss-120b model with Cerebas as the inference provider. You should use structured Outputs so that you can interpret the results and populate fiedls in the legal document.

There is an OPENROUTER_API_KEY in the .env file in the project root.

## Technical Design

The entire project should be packaged into a Docker container.
The Backend should be in backend/ and be a uv project, using FastAPI.
The frontend should be in frontend/
The database should use SQLLite and be created from scratch each time the Docker container is brought up, allowing for a suers table with a sign up and a sign in.
Consider statically building the frontend and serving it via FastAPI, if that will work.
There should be scripts in scripts/ for:
```bash
# Mac
scripts/start-mac.sh    # Start
scripts/stop-mac.sh     # Stop

# linux
scripts/start-linux.sh
scripts/stop-linux.sh

# Windows
scripts/start-windows.ps1
scripts/stop-windows.ps1
```
Backend available at http://localhost:8000

## Working documentation

All documents for planning and executing this project will be in the docs/ directory.
Please review the docs/PLAN.md document before proceeding.
	
## VERY IMPORTANT
- Be simple. Approach tasks in a simple, incremental way.
- Work incrementally ALWAYS. Small, simple steps. Validate and check each increment before moving on.
- Use LATEST apis of NOW
## MANDATORY Code Style
- Do not overengineer. Do not program defensively. Use exception managers only when needed.
- Identify root cause before fixing issues. Prove with evidence, then fix.
- Work incrementally with small steps. Validate each increment.
- Use latest library APIs.
- Use 'uv' as Python package manager. ALways 'uv run xxx' never 'python3 xxx', always 'uv add xxx' never 'pip instal xxx'
- Favor clear, concise docstring comments. Be sparing with comments outside docstrings.
- Favor short modules, short methods and functions. Name things clearly.
- Never use emojis in code or in print statements or logging
- Keep README.md concise
## Important - debugging and fixing
- When troubleshooting problems, ALWAYS identify root cause BEFORE fixing
- Reproduce consistently
- PROOVE THE PROBLEM FIRST - do not guess.
- Try one test at a time. Be methodical.
- Don't jump to conclusions. DO not apply workarounds.
