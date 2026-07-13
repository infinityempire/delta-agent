# Repository Creation Instructions

## Issue: Token Permissions

Your current GitHub token (`GH_TOKEN`) does not have the `repo` scope required to create repositories.

## Solution 1: Create Repository Manually (Quick)

1. Go to: https://github.com/new
2. Repository name: `zeta-agent`
3. Description: `Zeta - Multi-Agent Reddit Marketing & Distribution System`
4. Select: Public
5. Click "Create repository"

Then push your code:

```bash
cd /workspace/reddit_distributor_agent
git remote add origin https://github.com/infinityempire/zeta-agent.git
git push -u origin main
```

## Solution 2: Generate New Token with Proper Scopes

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: `zeta-agent-token`
4. Scopes: Select `repo` (full control)
5. Click "Generate token"
6. Copy the token and update your environment

Then run:
```bash
cd /workspace/reddit_distributor_agent
gh repo create zeta-agent --public --source=. --push
```

## Verification

After pushing, verify at: https://github.com/infinityempire/zeta-agent
