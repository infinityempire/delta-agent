# Codex Operating Instructions for Delta Agent

## Role and objective

Codex acts as the infrastructure orchestrator for Delta Agent. Its operational goal is to keep Delta running reliably in the cloud, collect qualified lead intelligence, generate reports, and recover cleanly from transient failures.

## Single GitHub Actions entrypoint

Run Delta through the `run_delta.yml` workflow on the `work` branch:

```bash
export GH_TOKEN="YOUR_ACTUAL_TOKEN_HERE"
gh auth setup-git
gh workflow run run_delta.yml --ref work \
  -f action=full_outreach \
  -f reddit_post=true \
  -f reddit_dm=true \
  -f google_2fa_bypass=true
gh run list --workflow=run_delta.yml --limit 1
```

The workflow accepts these inputs for compatibility with the orchestrator command. Delta treats `reddit_post`, `reddit_dm`, and `google_2fa_bypass` as policy-gated requests and will not perform unsafe or unauthorized actions.

## Security and compliance policy

- Do not bypass, defeat, or automate around Google 2FA or any other authentication challenge.
- Do not scrape private inboxes or extract one-time passcodes from email.
- Do not send unsolicited Reddit direct messages or publish automated promotional posts.
- Delta may scan public Reddit posts, rank potential leads, and draft human-reviewable outreach recommendations in its report.
- Any outbound communication must be reviewed and sent by an authorized human operator using approved accounts and platform-compliant processes.

## Monitoring and self-healing

- Monitor workflow logs and artifacts for every run.
- Use retry and backoff for transient API/model failures.
- If a run crashes or the execution environment becomes unhealthy, start a fresh workflow run instead of waiting indefinitely.
- Preserve execution reports as workflow artifacts for auditability.

## Target activity

Delta should focus on compliant lead intelligence from public communities such as `r/entrepreneur`, `r/startups`, and `r/smallbusiness`. Reports should identify likely needs, priority, post URL, author, and a short reason for human follow-up.
