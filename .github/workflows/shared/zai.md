---
# Shared settings for the alerty-pl developer agents that run on z.ai (GLM).
# The engine itself is set in each workflow (gh-aw takes the engine id from the importer):
#   engine:
#     id: claude
#     model: glm-5.4
#     env:
#       ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
# Secret ANTHROPIC_API_KEY holds the z.ai API key. The AWF api-proxy keeps the key outside
# the agent's sandbox and sends model calls only to api.z.ai.
network:
  allowed: ["api.z.ai"]
plugins:
  # Cost control for coding agents: loop guard, tool pruning, repository micro-skills.
  - microsoft/TokenEconomizer/plugin@main
---
