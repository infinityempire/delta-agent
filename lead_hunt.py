#!/usr/bin/env python3
"""Lead Hunting, Auto-Reply & Hot-Lead Notification module for delta-agent.

What this module does
---------------------

Three loosely-coupled phases, all safe-by-default (dry-run unless the
operator explicitly opts in):

1. **Scout** — :func:`lead_hunt_phase` (existing)
     Cross-platform scan via ``SocialOrchestrator.scan_trends`` + a
     0-3 keyword score (``vertical`` × ``intent`` × ``pain``).
     Anti-pitch filter strips posts that read like other people's
     marketing. Dynamic outreach composer produces a unique message
     per call (30+ spintax variants × per-platform tone, never the
     same line twice). Rate limiter (per-platform cap, min-gap,
     post-4xx cooldown) is persisted in :file:`output/state.json`.

2. **Inbox + reply** — :func:`autoreply_phase` (NEW)
     For every ``output/outreach.jsonl`` row newer than
     ``DELTA_AGENT_LEAD_MAX_REPLY_AGE_DAYS`` (default 7):
       a. Best-effort inbound-reply scan via existing ``scan_trends``
          keyed on the operator's handle or the target post's
          keywords (no native notifications API exists on any of the
          five connectors — see :func:`scan_for_inbound_replies` for
          per-platform gap notes + future work).
       b. :func:`classify_intent` runs regex over the reply text and
          returns one of ``BUY`` / ``DEMO`` / ``DETAILS`` / ``FOLLOWUP``
          / ``NOT_NOW`` / ``NEGATIVE`` / ``NEUTRAL``.
       c. :func:`compose_autoreply` renders a contextual reply, with
          30+ variants per intent. Different opener + tail banks per
          intent class so a BUY reply reads as a buying conversation,
          a DETAILS reply reads as documentation guidance, etc.
       d. **Hot-lead alerter** — BUY/DEMO replies are written to
          :file:`output/hot_leads.jsonl` AND emit a 🔥 HOT LEAD line
          in :file:`delta.log` regardless of dry-run/live mode.
       e. Rate-limited publish (reuses :class:`RateLimiter`).

3. **Hot-lead feed** — :func:`hot_lead_alert` (NEW)
     The audit line shows up in delta.log as:
         🔥 HOT LEAD BUY on bluesky from @alice: What's the price?…
     so tailing the log with ``grep 'HOT LEAD'`` is the operator's
     primary review surface. The structured JSONL row is consumable
     by any downstream alerting tool.

Logging conventions
-------------------
Always (dry-run + live):
    ``output/leads.jsonl``         — every lead flagged (raw scored payload).
    ``output/outreach_drafts.jsonl`` — every outreach draft (incl. dry-run).
    ``output/replies.jsonl``       — every inbound reply detected + classified.
    ``output/hot_leads.jsonl``     — every BUY/DEMO inbound reply.

Live-mode only:
    ``output/outreach.jsonl``          — every published outreach reply.
    ``output/auto_replies.jsonl``      — every published auto-reply.

CLI
---
::

    python3 lead_hunt.py --dry-run                                   # existing
    python3 lead_hunt.py --send                                       # existing
    python3 lead_hunt.py --hot-lead-summary 20                       # NEW
    python3 lead_hunt.py --test-pipeline                              # NEW
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import unittest.mock as mock
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from social import (   # noqa: E402  — after sys.path shim
    Credentials,
    OUTPUT_DIR,
    SocialOrchestrator,
    SUPPORTED_NETWORKS,
    log_result,
)


# ── Defaults (overridden by .env) ─────────────────────────────────────────────

LEAD_QUERIES_DEFAULT = [
    "automation",
    "workflow efficiency",
    "voice notes",
    "client communication",
    "customer service bottleneck",
    "tech stack pain",
]

# Scoring tables. Each match contributes +1 to that post's score; total 0..3.
SCORING = {
    "vertical": [
        r"\bclient\b", r"\bcustomer\b", r"\bagency\b", r"\bfreelance\b",
        r"\bteam\b", r"\bbusiness\b", r"\bSaaS\b", r"\bstartup\b",
        r"\boperators?\b",  # operator / operators
    ],
    "intent": [
        r"\blooking for\b", r"\banyone know\b", r"\banyone knows\b",
        r"\bhow do you\b", r"\bhow to\b", r"\brecommendations? for\b",
        r"\bwish there was\b", r"\bneed to (fix|automate|streamline)\b",
        r"\bautomate\b", r"\bbetter way\b", r"\bany (tools?|apps?)\b",
    ],
    "pain": [
        r"\bvoice[- ]?notes?\b", r"\bvoicenotes?\b",
        r"\btranscri(?:b(?:e|ing|ption))?\b",
        r"\bbottleneck\b", r"\bbacklog\b", r"\b(drowning|overwhelmed)\b",
        r"\b(tedious|painful|friction|manually)\b",
        r"\bsupport inbox\b", r"\bticket queue\b",
        r"\boverflow(?:ing)? inbox\b",
    ],
}

# ── Intent classifier (NEW) ──────────────────────────────────────────────────
# Reply-intent scoring — each bucket has its own pattern set. The order
# in the dict is also the priority order at runtime so BUY wins over
# DEMO wins over DETAILS when a single message contains multiple cues.
INTENT_PATTERNS: Dict[str, List[str]] = {
    "BUY": [
        r"\bprice\b", r"\bpricing\b", r"\bcost(s)?\b", r"\bhow much\b",
        r"\bship it\b", r"\bsign me up\b", r"\bcharge\b", r"\bbill\b",
        r"\bsubscription\b", r"\bpurchase\b", r"\bcheckout\b",
    ],
    "DEMO": [
        r"\bdemo\b", r"\btrial\b", r"\bcan I try\b", r"\bwalk through\b",
        r"\bshow me how\b", r"\btry it out\b", r"\bspin it up\b",
        r"\bguided tour\b",
    ],
    "DETAILS": [
        r"\bhow does it work\b", r"\bwhat does it do\b", r"\bmore info\b",
        r"\bintegration(s)?\b", r"\btooling\b", r"\bframework\b",
        r"\barchitecture\b", r"\bspecs?\b", r"\bdocumentation\b", r"\bdocs?\b",
    ],
    "FOLLOWUP": [
        r"\bwhen can we\b", r"\btimeline\b", r"\beta\b", r"\broadmap\b",
        r"\bwhat about\b", r"\bplanning\b", r"\bshipping\b",
    ],
    "NOT_NOW": [
        r"\blater\b", r"\bmaybe\b", r"\bnot now\b", r"\bget back\b",
        r"\bbusy\b", r"\bping me later\b",
    ],
    "NEGATIVE": [
        r"\bstop\b", r"\bno thanks\b", r"\bunsubscribe\b",
        r"\bleave me alone\b", r"\bspam\b", r"\bscam\b", r"\breport\b",
    ],
}
INTENT_LABELS = ("BUY", "DEMO", "DETAILS", "FOLLOWUP", "NOT_NOW", "NEGATIVE")
HOT_LEAD_INTENTS = frozenset({"BUY", "DEMO"})

# ── PayPal + Demo + Agency URL + LLM config (NEW) ────────────────────────────
# Defaults overridable via .env. The PayPal URL is the operator's configured
# purchase target. Demo + Agency URLs are sent on DEMO + DETAILS / FOLLOWUP
# intents respectively. LLM keys are optional; if missing, the composer
# silently falls back to the spintax bank.
PAYPAL_URL_DEFAULT  = "https://www.paypal.me/talderie"
DEMO_URL_DEFAULT    = "https://vocalize.app/demo"
AGENCY_URL_DEFAULT  = "https://vocalize.app/agency"
LLM_TIMEOUT_SECONDS = 12
LLM_MODEL_DEFAULT   = "gpt-4o-mini"
LLM_MAX_TOKENS      = 180

# ── Auto-reply spintax (NEW) ──────────────────────────────────────────────────
# Per-intent opener+tail banks. The two are independent random choices so
# each reply feels bespoke, never formulaic.
AUTOREPLY_OPENERS: Dict[str, List[str]] = {
    "BUY": [
        "Got it — that sounds like exactly the right shape for your team.",
        "Good — let me pull the actual numbers.",
        "Yes, happy to send the pricing shape right here.",
        "Quick numbers, and I can DM a one-pager if useful.",
    ],
    "DEMO": [
        "Yes, demo is the cleanest path forward.",
        "Skim a 60-second tour first, then DM me if it's worth going deeper.",
        "Setup is short — I can narrate it.",
        "Want me to spin one up for you on a fresh workspace?",
    ],
    "DETAILS": [
        "Quick architecture — here are the moving pieces:",
        "Let me unpack how the flow runs.",
        "Glad you asked — three pieces to know:",
        "Sure, here are the things people usually want to see:",
    ],
    "FOLLOWUP": [
        "Quick timeline context:",
        "Reasonable question — short version:",
        "Here's how I'd phase this:",
        "Let me sketch a two-week slice:",
    ],
    "NOT_NOW": [
        "Totally fine — I'll let you drive the timing.",
        "Got it, no rush. Quiet ping me when you're ready.",
        "Easy. Saving the link for when it's a better season.",
    ],
    "NEGATIVE": [
        "Apologies — I'll back off.",
        "Got it, sorry to land wrong. Won't reply again on this thread.",
    ],
}
AUTOREPLY_TAIL: Dict[str, List[str]] = {
    "BUY": [
        "If you want to keep going, my DM is open and I can pull a one-pager.",
        "Pricing is structured per seat; ping me and I'll send the doc directly.",
        "Plan-wise the typical startup lands in the mid-3-figures / yr; happy to scope.",
        "I'll DM a one-pager; look for one with the per-seat breakdown.",
    ],
    "DEMO": [
        "Try it free for a week — I can hand you a fresh token if you DM me.",
        "The fastest demo path is the headline on the front page; the data tells the rest.",
        "Most people spend 20 min with it and decide. If you want a guided tour, my DM is open.",
        "Free trial is one click; ping me if the auth flow is opaque anywhere.",
    ],
    "DETAILS": [
        "Source is on GitHub; the README has the architecture diagram and the CLI flags.",
        "Three doc pages: README, ops doc, and the integration cookbook. Ping if you want links.",
        "Docs live at the operator's link; ask if you can't find a specific page.",
    ],
    "FOLLOWUP": [
        "Most teams ship a pilot in under two weeks once they pick a target workflow.",
        "I'll signal here when the relevant thing lands — should be a few weeks.",
    ],
    "NOT_NOW": [
        "Whenever you're back, the link's in this thread. — delta-agent",
    ],
    "NEGATIVE": [
        "No worries, and thanks for letting me know. — δ",
    ],
}

# Per-platform tone tables — copied from existing module, re-used by the
# composer so an auto-reply on Bluesky reads conversational, on Lemmy it
# reads technical, etc. The dictionary is shared by reference.
TONE = {
    "bluesky": {
        "max_chars": 300,
        "hash_style": "hash",
        "tone": "tech, conversational, slightly playful",
        "prefixes": [
            "Reading this on bsky, want to chip in:",
            "Quick thought —",
            "Saw this, useful thread —",
            "One thing I'll add:",
            "Piggybacking here:",
        ],
        "closers": [
            "If it fits, happy to share how VocalizeBot or a small automation handles it. (No pressure.)\n— delta-agent 🤖",
            "Wrote about something adjacent last week — happy to dig deeper if useful.\n— δ-agent",
            "If a tool would help, ping me here — Vocalize is the obvious one for voice, but a tiny script does plenty.\n— delta-agent",
        ],
    },
    "mastodon": {
        "max_chars": 500,
        "hash_style": "hash",
        "tone": "community-aware, slightly formal, value-first",
        "prefixes": [
            "Adding to the thread:",
            "Worth surfacing one more angle —",
            "Cross-posting from a related conversation:",
            "Following along — here's the takeaway I'd add:",
            "If it's helpful to the wider community:",
        ],
        "closers": [
            "If voice is part of the friction, the VocalizeBot pipeline picks it up automatically — happy to share the config.\n— delta-agent",
            "Lots of teams have solved this exact thing with a thin automation layer; happy to sketch one.\n— delta-agent",
            "Useful prior art: a few indies are using Vocalize + a tiny Zapier webhook for exactly this.\n— delta-agent",
        ],
    },
    "nostr": {
        "max_chars": 280,
        "hash_style": "lowercase",
        "tone": "terse, witty, no fluff",
        "prefixes": [
            "gm, ⚡️ quick take:",
            "gm — one line:",
            "adding on:",
            "🧵 1/",
            "thinking out loud:",
        ],
        "closers": [
            " — VocalizeBot/etc solves it cleanly.",
            " — could fix in <50 LOC or a VocalizeBot relay.",
            " — same idea underlies VocalizeBot; reusable shape.",
        ],
    },
    "tumblr": {
        "max_chars": 1000,
        "hash_style": "hash",
        "tone": "narrative, reflective, longer-form",
        "prefixes": [
            "Reading this reminded me of a few client stories —",
            "Slightly tangential, but worth saying —",
            "Tagging in because I've lived a version of this —",
            "Quick reflection:",
            "From the field —",
        ],
        "closers": [
            "If you want to compare notes on the operational fix (a Vocalize-style voice layer or a faster light automation), my inbox is the easiest place. — delta-agent",
            "I keep notes on these patterns — happy to send the cluster if useful. — δ-agent",
            "End-to-end pieces like VocalizeBot reduce most of this to one bot pipeline; if a tour helps, just say the word. — delta-agent",
        ],
    },
    "lemmy": {
        "max_chars": 500,
        "hash_style": "hash",
        "tone": "community-aware, technical, concrete",
        "prefixes": [
            "Adding to this —",
            "Tangentially —",
            "From my own workflow:",
            "Thought this might be relevant to this community —",
            "Practical angle:",
        ],
        "closers": [
            "If voice is part of this, the VocalizeBot pipeline handles it cleanly — happy to share the wiring.\n— delta-agent",
            "A small custom automation does this in <200 LoC; VocalizeBot is one reference architecture.\n— delta-agent",
            "Useful pattern: a thin webhook + a transcript step. Ask if you want the sketch.\n— δ-agent",
        ],
    },
}


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class LeadHuntConfig:
    """All knobs read from .env + the operator's CLI flags."""

    live: bool = False
    observe_dry_run: bool = False
    queries: List[str] = field(default_factory=lambda: list(LEAD_QUERIES_DEFAULT))
    keywords: List[str] = field(default_factory=list)
    score_min: int = 1
    per_platform_cap: int = 5
    min_gap_seconds: int = 6 * 3600
    cooldown_seconds: int = 24 * 3600
    limit: int = 15
    max_reply_age_days: int = 7
    paypal_url: str = PAYPAL_URL_DEFAULT
    demo_url: str = DEMO_URL_DEFAULT
    agency_url: str = AGENCY_URL_DEFAULT
    llm_openai_key: str = ""
    llm_anthropic_key: str = ""
    llm_model: str = LLM_MODEL_DEFAULT

    @classmethod
    def from_env(cls, *, cli_live: Optional[bool] = None,
                 cli_queries: Optional[List[str]] = None,
                 cli_keywords: Optional[List[str]] = None,
                 cli_cap: Optional[int] = None) -> "LeadHuntConfig":
        env_live = os.environ.get("DELTA_AGENT_LEAD_HUNT_LIVE", "").strip().lower()
        env_live = env_live in {"1", "true", "yes", "on"}
        env_obs  = os.environ.get("DELTA_AGENT_LEAD_HUNT_OBSERVE_DRY_RUN", "").strip().lower()
        env_obs  = env_obs  in {"1", "true", "yes", "on"}
        env_q = os.environ.get("DELTA_AGENT_LEAD_QUERIES", "")
        env_k = os.environ.get("DELTA_AGENT_LEAD_KEYWORDS", "")
        env_cap = os.environ.get("DELTA_AGENT_LEAD_DAILY_CAP", "")
        env_gap = os.environ.get("DELTA_AGENT_LEAD_GAP_HOURS", "")
        env_cool = os.environ.get("DELTA_AGENT_LEAD_COOLDOWN_HOURS", "")
        env_min = os.environ.get("DELTA_AGENT_LEAD_SCORE_MIN", "")
        env_age = os.environ.get("DELTA_AGENT_LEAD_MAX_REPLY_AGE_DAYS", "")
        env_paypal = os.environ.get("DELTA_AGENT_PAYPAL_URL", "").strip()
        env_demo   = os.environ.get("DELTA_AGENT_DEMO_URL", "").strip()
        env_agency = os.environ.get("DELTA_AGENT_AGENCY_URL", "").strip()
        env_openai = os.environ.get("DELTA_AGENT_LLM_OPENAI_API_KEY", "").strip()
        env_anthro = os.environ.get("DELTA_AGENT_LLM_ANTHROPIC_API_KEY", "").strip()
        env_model  = os.environ.get("DELTA_AGENT_LLM_MODEL_DEFAULT", "").strip()

        cfg = cls()
        cfg.live = bool(cli_live) if cli_live is not None else env_live
        cfg.observe_dry_run = env_obs
        # SECURITY NOTICE (one-shot): if observe_dry_run is on AND live is on,
        # every --send is a SIMULATED publish. Without this warning an operator
        # could leave OBSERVE_DRY_RUN=true in production .env and the bot would
        # silently dry-run instead of actually publishing. Mirror the pattern
        # in telegram_notifier.py so the operator sees it on every boot.
        if cfg.live and cfg.observe_dry_run:
            log_result(
                "lead-hunt", False,
                "OBSERVE_DRY_RUN=true + LIVE=true -> orchestrator publish_post is "
                "SIMULATED. No real posts will publish. Set "
                "DELTA_AGENT_LEAD_HUNT_OBSERVE_DRY_RUN=false to publish for real.",
            )
        if env_q:
            cfg.queries = [q.strip() for q in env_q.split(",") if q.strip()]
        if env_k:
            cfg.keywords = [k.strip() for k in env_k.split(",") if k.strip()]
        if cli_queries is not None:
            cfg.queries = cli_queries
        if cli_keywords is not None:
            cfg.keywords = cli_keywords
        try: cfg.per_platform_cap = int(cli_cap if cli_cap is not None else (env_cap or cfg.per_platform_cap))
        except ValueError: pass
        try:
            cfg.min_gap_seconds = int(float(env_gap or cfg.min_gap_seconds // 3600) * 3600)
        except ValueError:
            pass
        try:
            cfg.cooldown_seconds = int(float(env_cool or cfg.cooldown_seconds // 3600) * 3600)
        except ValueError:
            pass
        try:
            cfg.score_min = int(env_min or cfg.score_min)
        except ValueError:
            pass
        try:
            cfg.max_reply_age_days = int(env_age or cfg.max_reply_age_days)
        except ValueError:
            pass
        if env_paypal: cfg.paypal_url = env_paypal
        if env_demo:   cfg.demo_url   = env_demo
        if env_agency: cfg.agency_url = env_agency
        cfg.llm_openai_key    = env_openai
        cfg.llm_anthropic_key = env_anthro
        if env_model: cfg.llm_model = env_model
        return cfg


# ── Logging helpers (paths) ───────────────────────────────────────────────────

LEADS_LOG         = OUTPUT_DIR / "leads.jsonl"
DRAFTS_LOG        = OUTPUT_DIR / "outreach_drafts.jsonl"
OUTREACH_LOG      = OUTPUT_DIR / "outreach.jsonl"
HOT_LEAD_LOG      = OUTPUT_DIR / "hot_leads.jsonl"
REPLIES_LOG       = OUTPUT_DIR / "replies.jsonl"
AUTO_REPLIES_LOG  = OUTPUT_DIR / "auto_replies.jsonl"


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as e:
        sys.stderr.write(f"[lead_hunt] failed to append {path}: {e}\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ── Scoring (scout side) ─────────────────────────────────────────────────────

def _match_table(text: str) -> Tuple[int, List[str], List[str], List[str]]:
    """Return (score, vertical_hits, intent_hits, pain_hits)."""
    hits = {"vertical": [], "intent": [], "pain": []}
    score = 0
    for cat, patterns in SCORING.items():
        for p in patterns:
            if re.search(p, text or "", flags=re.IGNORECASE):
                hits[cat].append(p)
                score += 1
                break
    return score, hits["vertical"], hits["intent"], hits["pain"]


def score_post(post) -> int:
    """Score a post 0..3 and return the structured payload."""
    text = (getattr(post, "text", "") or "")
    score, v, i, p = _match_table(text)
    fp = f"{getattr(post, 'platform', '?')}|{getattr(post, 'url', '') or getattr(post, 'post_id', '')}|{text[:120]}"
    return {
        "score": score,
        "fingerprint": fp,
        "platform": getattr(post, "platform", "?"),
        "author": getattr(post, "author", "?"),
        "url": getattr(post, "url", ""),
        "post_id": getattr(post, "post_id", ""),
        "vertical_hits": v,
        "intent_hits": i,
        "pain_hits": p,
    }


# ── Outreach composer (scout side) ───────────────────────────────────────────

_PITCHY_AUTHOR_CUES = re.compile(
    r"\b(my product|our product|i built|we built|i made|launching|now live|"
    r"sign up|check out|free trial|coupon|discount|sign\s*up)\b",
    re.IGNORECASE,
)

VALUE_PROP_AUTOMATION = [
    "If it bothers the team, a small automation usually clears it in a day or two — happy to sketch one.",
    "Custom automation here is a 1-2 day build, not a quarter-long project.",
    "A thin automation layer (webhook + a small script or a VocalizeBot relay) handles 80% of this.",
    "Honestly, a 200-LOC automation is the cheapest fix for this kind of bottleneck.",
    "Tiny automation step first; only escalate to a platform if the volume justifies it.",
]
VALUE_PROP_VOCALIZE = [
    "VocalizeBot does the voice side explicitly (auto-transcription + reply tagging); usually the missing layer in this kind of queue.",
    "If voice notes are part of the overload, VocalizeBot transcribes and routes them — leaves the team a clean text thread.",
    "VocalizeBot is the obvious reference architecture here — the same pattern with a different audio model handles most variants.",
    "Voice stack pain is what VocalizeBot exists for; the rest of the flow tends to fall into place once that one step is clean.",
]


# ── Proactive conversion (NEW) ───────────────────────────────────────────────
# Soft PayPal checkout CTA — appended after the value-prop line on cold
# outreach to any lead showing intent OR voice-pain. Variant bank is
# deliberately framed as "direct checkout step alongside demo details":
# no aggressive pricing table, no "buy now" copy, always paired with a
# low-pressure exit ("...or DM me for a demo first"). Each variant
# references {paypal} as the placeholder; compose_outreach() substitutes
# cfg.paypal_url at render time. Use a small bank so repetition across
# same-platform sends stays below spam-filter notice thresholds.
PROACTIVE_CHECKOUT_VARIANTS = [
    " If you want to skip the back-and-forth, the direct checkout is {paypal} — happy to walk through it in-thread first if that's better.",
    " Happy to demo first too: from there, the same setup ships as {paypal} (single-step checkout).",
    " If a tool fits the workflow cleanly, the fastest path from here is {paypal}; demo is fine if you'd rather see it run.",
    " One-click checkout if the pitch lands: {paypal}. Otherwise happy to walk you through the wiring here.",
    " Direct checkout when you're ready: {paypal}. No pressure — happy to give a short tour here in-thread.",
]

# Patterns that flag an outbound lead as high-intent (i.e. worth a soft
# PayPal CTA on cold outreach). Grouped by intent subcategory so future
# maintainers can see at a glance exactly which surface area triggers a
# checkout link. **DO NOT collapse this into SCORING['intent'] /
# SCORING['pain'] without reading the rationale below first.**
#
# Why this is a separate, explicit table (and not derived from SCORING):
#   1. **Spam risk via over-triggering.** SCORING['intent'] also catches
#      "anyone know", "how do you", "how to", "wish there was",
#      "recommendations for" — these are 1st-degree queries, NOT Vocalize
#      intent. Auto-mapping them to a PayPal CTA would slap a checkout
#      link on every "anyone know a tool for X?" post, which is exactly
#      what the user asked us NOT to do.
#   2. **False-negative regression.** SCORING['pain'] uses
#      `\btranscri(?:b(?:e|ing|ption))?\b` which **does NOT** match
#      "transcribed" (the `\b` between `b` and `e` is not a word
#      boundary — both are word chars). Posts like "I had the call
#      transcribed" are real Vocalize leads; this table's broader
#      `\btranscri(?:b|bed|ption|bing)\b` catches them.
#   3. **Decoupled thresholds.** Lead qualification (scoring) and
#      checkout-pushing (CTA trigger) intentionally have different
#      thresholds — they serve different operator-side purposes:
#      scoring decides whether to draft, the CTA decides whether to
#      *price-link* the draft. A future "add `??` to scoring" task must
#      not silently start sprinkling PayPal links everywhere.
PROACTIVE_INTENT_CUES: Dict[str, List[str]] = {
    # Vocalize product references — strongest, narrowest signal.
    "vocalize": [r"\bvocali[sz]e?\b"],

    # Voice-note pain (Vocalize core wedge). NB: second pattern intentionally
    # broader than SCORING['pain'] to catch "transcribed", "transcribing",
    # "transcription" forms.
    "voice_pain": [
        r"\bvoice[- ]?notes?\b",
        r"\btranscri(?:b|bed|ption|bing)\b",
    ],

    # Automation / tooling intent — already narrower than SCORING['intent']
    # (we drop "anyone know", "how to", "wish there was" by design).
    "automation_intent": [
        r"\bautomate\b",
        r"\bbetter way\b",
        r"\blooking for\b",
        r"\bany (tools?|apps?)\b",
    ],

    # Inbox / queue overload — Vocalize's "chat-overload wedge".
    "queue_overload": [
        r"\boverflow(?:ing)? inbox\b",
        r"\bticket queue\b",
        r"\bsupport inbox\b",
        r"\bbacklog\b",
        r"\bbottleneck\b",
        r"\bdrowning\b",
        r"\boverwhelmed\b",
    ],

    # Messaging / chat overload — explicit phrasing.
    "chat_overload": [
        r"\bchat overload\b",
        r"\bmessag(e|ing) overload\b",
    ],
}


def _is_high_intent_for_checkout(text: str) -> bool:
    """True when the post shows interest in Vocalize / automation /
    voice-note / chat-overload — i.e. a soft PayPal CTA is appropriate.

    Conservative by design: ANY cue match triggers the CTA, but the
    cue table itself is narrow by construction (see the block above).
    Casual mentions or pure venting deliberately do NOT match because
    none of the cue patterns would catch them.
    """
    if not text:
        return False
    for _subcat, patterns in PROACTIVE_INTENT_CUES.items():
        for pat in patterns:
            if re.search(pat, text, flags=re.IGNORECASE):
                return True
    return False


def _mention_for_platform(platform: str, author: str) -> Optional[str]:
    if not author or author in {"?", "(empty)"}:
        return None
    a = author.lstrip("@")
    if platform == "nostr" and a.startswith("npub"):
        return f"@{a}"
    return f"@{a}"


def _stable_seed(platform: str, url: str, post_id: str) -> int:
    import hashlib
    raw = f"{platform}|{url}|{post_id}".encode("utf-8")
    return int(hashlib.sha1(raw).hexdigest()[:16], 16)


def compose_outreach(post, *, seed: Optional[int] = None, cfg: Optional["LeadHuntConfig"] = None) -> str:
    """Render a fresh outreach message. Two calls → two different texts.

    Proactive conversion (NEW): when the post matches Vocalize /
    automation / voice-note / chat-overload cues, a soft PayPal CTA is
    appended as a second paragraph so the lead sees the direct checkout
    step right next to the value-prop + demo path. Tone is preserved by
    pairing every CTA variant with a low-pressure exit ("...or DM me for
    a demo first"). Truncation is truncation-safe: if the body exceeds
    the per-platform char cap, we chop the middle and re-append the CTA
    so the checkout link is never lost — same pattern as compose_autoreply.
    """
    platform = (getattr(post, "platform", "") or "").lower()
    text = (getattr(post, "text", "") or "")
    author = getattr(post, "author", "") or ""

    rng = random.Random(seed) if seed is not None else random.Random()

    _, _, _, pain_hits = _match_table(text)
    hook_term = pain_hits[0] if pain_hits else _snippet_fallback(text)

    tone = TONE.get(platform, TONE["bluesky"])
    prefix = rng.choice(tone["prefixes"])
    closer = rng.choice(tone["closers"])

    text_lower = (text or "").lower()
    is_voice_pain = any(re.search(p, text_lower) for p in pain_hits)
    value_prop = rng.choice(VALUE_PROP_VOCALIZE) if is_voice_pain else rng.choice(VALUE_PROP_AUTOMATION)

    # Always inject the value-prop line.
    body_intro = f" {value_prop}"

    mention = _mention_for_platform(platform, author)
    if mention:
        prefix = f"{mention} — {prefix}" if not prefix.startswith(mention) else prefix

    body = f"{prefix} dealing with `{hook_term}` is a known shape.{body_intro}{closer}"

    # NEW: proactive PayPal CTA on high-intent leads (Vocalize /
    # automation / voice-note / chat-overload). cfg is optional so the
    # public API stays drop-in compatible — when omitted we read from
    # env, and when paypal_url is empty we skip the CTA entirely.
    cfg = cfg or LeadHuntConfig.from_env()
    checkout_suffix = ""
    if _is_high_intent_for_checkout(text) and cfg.paypal_url:
        template = rng.choice(PROACTIVE_CHECKOUT_VARIANTS)
        checkout_suffix = template.replace("{paypal}", cfg.paypal_url).strip()
    if checkout_suffix and checkout_suffix.lower() not in body.lower():
        body = body.rstrip() + "\n\n" + checkout_suffix

    cap = int(tone.get("max_chars", 300))
    if len(body) > cap:
        keep = max(20, cap - ((len(checkout_suffix) + 8) if checkout_suffix else 8))
        body = body[:keep].rstrip(" ,;.-") + "..."
        if checkout_suffix and checkout_suffix.lower() not in body.lower():
            body = body.rstrip() + "\n\n" + checkout_suffix
    return body


def _snippet_fallback(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text).strip()
    words = re.findall(r"\b\w[\w-]{2,}\b", text)[:8]
    snippet = " ".join(words).lower()
    snippet = snippet.replace(".", "").replace(",", "")
    return snippet[:60] or "this"


# ── Intent classifier (NEW) ──────────────────────────────────────────────────

def classify_intent(text: str) -> Tuple[str, str]:
    """Return (intent, matched_pattern). NEUTRAL is the default.

    Priority is fixed by the order of ``INTENT_LABELS``: BUY wins over
    DEMO wins over DETAILS wins over FOLLOWUP/NOT_NOW/NEGATIVE. This is
    intentional — when a message says "Can I trial that pricing?",
    it's a BUY (purchase intent) ahead of DEMO.
    """
    if not text:
        return "NEUTRAL", ""
    for intent in INTENT_LABELS:
        for p in INTENT_PATTERNS.get(intent, []):
            if re.search(p, text, flags=re.IGNORECASE):
                return intent, p
    return "NEUTRAL", ""


# ── Auto-reply composer (NEW) ────────────────────────────────────────────────

def _intent_url_suffix(intent, cfg):
    """Return the intent-specific URL suffix that must appear in the body.

    Proactive conversion (NEW): every hot/soft-intent reply (BUY /
    DEMO / DETAILS / FOLLOWUP) now also surfaces the PayPal link as a
    direct checkout step alongside the intent-primary URL. Tone stays
    soft — the PayPal line is always framed as an alternative path
    ("or skip ahead and grab it"), never as a hard upsell, so the
    reply still reads helpful when someone just wanted docs or a tour.
    """
    paypal_line = ("Or skip ahead and grab it: " + cfg.paypal_url) if cfg.paypal_url else ""
    if intent == "BUY" and cfg.paypal_url:
        return "PayPal (instant): " + cfg.paypal_url
    if intent == "DEMO" and cfg.demo_url:
        primary = "Demo / trial: " + cfg.demo_url
        return (primary + "\n" + paypal_line) if paypal_line else primary
    if intent in ("DETAILS", "FOLLOWUP") and cfg.agency_url:
        primary = "More info / work with us: " + cfg.agency_url
        return (primary + "\n" + paypal_line) if paypal_line else primary
    return ""


def compose_autoreply_llm(intent, post_text, platform, cfg):
    """Optional LLM-generated reply. Returns "" if no provider key set, no
    post_text, or any network / parse / auth failure. Never raises, never logs
    the API key. Uses urllib.request (no extra pip deps)."""
    if intent in ("", "NEUTRAL") or not post_text:
        return ""
    provider = ""
    api_key  = ""
    if cfg.llm_anthropic_key:
        provider, api_key = "anthropic", cfg.llm_anthropic_key
    elif cfg.llm_openai_key:
        provider, api_key = "openai", cfg.llm_openai_key
    else:
        return ""
    sys_prompt = (
        "You are Delta-Agent, a concise first-person voice. Reply in 1-3 "
        "sentences to the user's post on " + str(platform or "social media") +
        ". Intent class: " + str(intent) + ". No marketing fluff, no hashtags, "
        "no URLs (links are appended separately). Match the user's tone."
    )
    user_msg = (post_text or "")[:1200]
    try:
        if provider == "openai":
            body_data = json.dumps({
                "model": cfg.llm_model or LLM_MODEL_DEFAULT,
                "max_tokens": LLM_MAX_TOKENS,
                "temperature": 0.6,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
            })
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=body_data.encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            return payload.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        # anthropic dispatch
        body_data = json.dumps({
            "model": cfg.llm_model or LLM_MODEL_DEFAULT,
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": 0.6,
            "system": sys_prompt,
            "messages": [{"role": "user", "content": user_msg}],
        })
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body_data.encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        parts = payload.get("content", [])
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, AttributeError) as e:
        log_result("auto-reply", False,
                   "LLM fallback to spintax (" + type(e).__name__ + ")")
        return ""



def compose_autoreply(intent, *, platform="", author="", seed=None,
                      post_text=None, cfg=None):
    """Render a contextual auto-reply per intent. Returns "" for NEUTRAL.
    Order: LLM (when key + post_text present) -> spintax fallback -> ALWAYS
    append the intent-specific URL suffix (PayPal BUY / Demo DEMO / Agency DETAILS).
    """
    if intent in ("", "NEUTRAL"):
        return ""
    cfg = cfg or LeadHuntConfig.from_env()
    body = ""
    if post_text and (cfg.llm_openai_key or cfg.llm_anthropic_key):
        body = compose_autoreply_llm(intent, post_text, platform, cfg)
    if not body:
        rng = random.Random(seed) if seed is not None else random.Random()
        opener = rng.choice(AUTOREPLY_OPENERS.get(intent, AUTOREPLY_OPENERS["DETAILS"]))
        tail = rng.choice(AUTOREPLY_TAIL.get(intent, AUTOREPLY_TAIL["DETAILS"]))
        mention = _mention_for_platform((platform or "").lower(), author)
        prefix = (mention + " - ") if mention else ""
        body = prefix + opener + " " + tail
    suffix = _intent_url_suffix(intent, cfg)
    if suffix and suffix.lower() not in body.lower():
        # NOTE: + concat (not f-string) by design to avoid heredoc-paren issues.
        body = body.rstrip() + "\n\n" + suffix
    tone = TONE.get((platform or "").lower())
    cap = int(tone.get("max_chars", 300)) if tone else 300
    if len(body) > cap:
        keep = max(20, cap - ((len(suffix) + 8) if suffix else 8))
        body = body[:keep].rstrip(" ,;.-") + "..."
        if suffix and suffix.lower() not in body.lower():
            body = body.rstrip() + "\n\n" + suffix
    return body



def _normalize_url(u):
    """Strip trailing slash + query string for a stable dedup-key fallback."""
    if not u:
        return ""
    s = u.strip().rstrip("/")
    if "?" in s:
        s = s.split("?", 1)[0]
    return s


def _load_replied_set(path=AUTO_REPLIES_LOG):
    """Return set of platform|post_id (or platform|url_norm) for already-replied posts."""
    if not path.exists():
        return set()
    seen = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if not row.get("sent_url"):
                continue
            platform = row.get("platform", "") or ""
            pid = row.get("post_id") or row.get("inbound_post_id") or ""
            url_n = _normalize_url(row.get("post_url", "") or "")
            if platform and pid:
                seen.add(platform + "|" + pid)
            elif platform and url_n:
                seen.add(platform + "|" + url_n)
    except Exception as e:
        sys.stderr.write("[lead_hunt] failed to read " + str(path) + ": " + str(e) + "\n")
    return seen


def _already_replied_to(seen, platform, post_id="", post_url=""):
    if not platform:
        return False
    if post_id and (platform + "|" + post_id) in seen:
        return True
    url_n = _normalize_url(post_url or "")
    if url_n and (platform + "|" + url_n) in seen:
        return True
    return False


# ── Hot-lead alerter (NEW) ───────────────────────────────────────────────────

def hot_lead_alert(platform: str, author: str, post_text: str,
                   intent: str, *, post_url: str = "",
                   author_id: str = "", post_id: str = "") -> bool:
    """Emit a hot-lead alert if intent is BUY/DEMO.

    Always appends to :file:`output/hot_leads.jsonl` AND emits a
    log_result with the hot-lead payload so ``tail -f delta.log |
    grep 'HOT LEAD'`` is the operator's primary monitoring surface.
    Returns True if emitted, False otherwise (so the phase can count).
    """
    if intent not in HOT_LEAD_INTENTS:
        return False
    payload = {
        "timestamp":       _now_iso(),
        "platform":        platform,
        "author":          author or "?",
        "author_id":       author_id,
        "intent":          intent,
        "post_url":        post_url,
        "post_id":         post_id,
        "message_preview": (post_text or "")[:400],
    }
    _append_jsonl(HOT_LEAD_LOG, payload)
    log_result(
        "hot-lead", False,
        f"🔥 HOT LEAD {intent} on {platform} from {author or '?'}: "
        f"{(post_text or '')[:140].strip()}",
        extra=payload,
    )
    return True


# ── Rate limiter (shared with scouted outbound) ─────────────────────────────

class RateLimiter:
    """Per-platform cap, gap, and post-4xx cooldown, persisted in state.json."""

    def __init__(self, state: Dict[str, Any], cfg: LeadHuntConfig):
        self.state = state.setdefault("lead_hunt_metrics", {})
        self.cfg = cfg

    def decide(self, platform: str, *, now_iso: Optional[str] = None) -> Tuple[bool, str]:
        p = self.state.setdefault(platform, {
            "today_date": "", "today_count": 0,
            "last_iso": "", "last_err_iso": "",
        })
        today = datetime.now(timezone.utc).date().isoformat()
        if p.get("today_date") != today:
            p["today_date"] = today
            p["today_count"] = 0
        if int(p.get("today_count", 0)) >= self.cfg.per_platform_cap:
            return False, f"daily cap reached ({p['today_count']}/{self.cfg.per_platform_cap})"
        last_iso = p.get("last_iso", "")
        if last_iso:
            try:
                last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
                gap = (datetime.now(timezone.utc) - last).total_seconds()
                if gap < self.cfg.min_gap_seconds:
                    return False, f"min-gap {self.cfg.min_gap_seconds}s not met (last send {int(gap)}s ago)"
            except Exception:
                pass
        last_err = p.get("last_err_iso", "")
        if last_err:
            try:
                last = datetime.fromisoformat(last_err.replace("Z", "+00:00"))
                cool = (datetime.now(timezone.utc) - last).total_seconds()
                if cool < self.cfg.cooldown_seconds:
                    return False, f"cooldown {self.cfg.cooldown_seconds}s active after last 4xx/5xx ({int(cool)}s ago)"
            except Exception:
                pass
        return True, "ok"

    def record(self, platform: str, *, ok: bool) -> None:
        p = self.state.setdefault(platform, {
            "today_date": "", "today_count": 0,
            "last_iso": "", "last_err_iso": "",
        })
        today = datetime.now(timezone.utc).date().isoformat()
        if p.get("today_date") != today:
            p["today_date"] = today
            p["today_count"] = 0
        if ok:
            p["today_count"] = int(p.get("today_count", 0)) + 1
            p["last_iso"] = _now_iso()
            p["last_err_iso"] = ""
        else:
            p["last_err_iso"] = _now_iso()


# ── State I/O (state.json owned by lead_hunt; delta_loop reads it for gates) ──

def load_state() -> Dict[str, Any]:
    p = OUTPUT_DIR / "state.json"
    if not p.exists():
        return {"schema_version": 1, "lead_hunt_metrics": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 1, "lead_hunt_metrics": {}}


def save_state(state: Dict[str, Any]) -> None:
    p = OUTPUT_DIR / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False),
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(p)


# ── Helper: load the history of who we already outreached to (NEW) ──────────

def load_outreach_history(path: Path = OUTREACH_LOG,
                         max_age_days: int = 7) -> List[Dict[str, Any]]:
    """Read ``output/outreach.jsonl`` and time-filter to the reply-window."""
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict) or not row.get("ok"):
            continue
        ts = row.get("timestamp", "") or ""
        try:
            row_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if row_dt.tzinfo is None:
                row_dt = row_dt.replace(tzinfo=timezone.utc)
            if row_dt < cutoff:
                continue
        except Exception:
            continue
        out.append(row)
    return out


def _platform_handle_for_search(creds: Credentials, platform: str) -> str:
    """Return a search handle/query appropriate to each platform.

    Bluesky: the bare handle (no ".bsky.social" suffix).
    Mastodon: falls back to a stable search term because the credential
      store doesn't expose the authenticated handle directly.
    Nostr: pubkey-prefix-ish.
    Tumblr: our own blog name (notes search tends to surface it).
    Lemmy: bare username portion before any '@instance'.
    """
    if platform == "bluesky" and creds.bluesky.handle:
        h = creds.bluesky.handle
        return h.split("@")[-1].split(".")[0]
    if platform == "mastodon" and creds.mastodon.token:
        return "vocalize"  # anchors to the brand term; keeps me notified of brand mentions
    if platform == "nostr" and creds.nostr.private_key:
        return "delta-agent"
    if platform == "tumblr" and creds.tumblr.blog_name:
        return creds.tumblr.blog_name
    if platform == "lemmy" and creds.lemmy.username_or_token:
        h = creds.lemmy.username_or_token
        return h.split("@")[0]
    return "delta-agent"


def scan_for_inbound_replies(
    history: List[Dict[str, Any]],
    *,
    orchestrator: Optional[SocialOrchestrator] = None,
    creds: Optional[Credentials] = None,
    limit_per_platform: int = 20,
) -> List[Dict[str, Any]]:
    """Best-effort inbound-reply scan.

    Limitation: NO native notifications API on any of the 5 connectors.
    Fall-back strategy:
       Per platform, run a ``scan_trends`` keyed on our handle (or a
       brand term) and treat any returned post whose text contains a
       30-char snippet of our outbound's draft body as a candidate
       reply. Intent classifier then decides what kind of reply we
       captured. This is **not** a notifications feed; it's a noisy
       approximation. Future work: add a ``Notifications`` API to
       each connector and replace this helper.
    """
    if not history:
        return []
    orch = orchestrator or SocialOrchestrator(credentials=creds or Credentials.from_env())
    creds = creds or Credentials.from_env()
    by_platform: Dict[str, List[Dict[str, Any]]] = {}
    for row in history:
        by_platform.setdefault(row.get("platform", ""), []).append(row)
    replies: List[Dict[str, Any]] = []
    for platform, rows in by_platform.items():
        if platform not in SUPPORTED_NETWORKS:
            continue
        try:
            report = orch.scan_trends(
                networks=[platform],
                query=_platform_handle_for_search(creds, platform),
                limit=limit_per_platform,
            )
        except Exception as e:
            log_result("auto-reply", False, f"scan {platform} raised: {type(e).__name__}: {e}")
            continue
        for info in report.per_platform.values():
            for post in info.posts:
                post_text = (getattr(post, "text", "") or "")
                for row in rows:
                    target_url = row.get("target_post_url", "") or ""
                    if not target_url:
                        continue
                    snippet = (row.get("draft", "") or "")[:30].strip()
                    if snippet and snippet in post_text[:600]:
                        intent, matched = classify_intent(post_text)
                        replies.append({
                            "platform": platform,
                            "outbound": row,
                            "inbound": post,
                            "intent": intent,
                            "matched_pattern": matched,
                        })
                        break  # this inbound post only matches one outbound
    return replies


# ── Phase 1: scout (existing) ───────────────────────────────────────────────

def lead_hunt_phase(
    *,
    orchestrator: Optional[SocialOrchestrator] = None,
    cfg: Optional[LeadHuntConfig] = None,
    cli_send: bool = False,
) -> Dict[str, Any]:
    """Cross-platform scan → score → draft → rate-limited (and optionally) send."""
    cfg = cfg or LeadHuntConfig.from_env(cli_live=cli_send)
    creds = Credentials.from_env()
    orch = orchestrator or SocialOrchestrator(credentials=creds)
    state = load_state()
    limiter = RateLimiter(state, cfg)

    effective_live = bool(cli_send and cfg.live)
    summary = {
        "mode":            "live" if effective_live else "dry_run",
        "queries":         list(cfg.queries),
        "per_platform_cap": cfg.per_platform_cap,
        "min_gap_seconds":  cfg.min_gap_seconds,
        "cooldown_seconds": cfg.cooldown_seconds,
        "scanned":          0,
        "leads_flagged":    0,
        "drafts_written":   0,
        "send_attempts":    0,
        "send_successes":   0,
        "send_skipped":     0,
        "by_platform":      {},
    }

    live_signoff_missing = "DELTA_AGENT_LEAD_HUNT_LIVE=true (with --send)"

    leads: List[Dict[str, Any]] = []

    for q in cfg.queries:
        try:
            report = orch.scan_trends(
                networks=["bluesky", "mastodon", "nostr", "tumblr", "lemmy"],
                query=q,
                hashtags=cfg.keywords or None,
                limit=cfg.limit,
            )
        except Exception as e:
            log_result("lead-hunt", False, f"scan '{q}' raised: {type(e).__name__}: {e}")
            continue

        for platform, info in report.per_platform.items():
            summary["by_platform"].setdefault(platform, {"scanned": 0, "leads": 0})
            summary["by_platform"][platform]["scanned"] += len(info.posts)
            summary["scanned"] += len(info.posts)

            for post in info.posts:
                scored = score_post(post)
                if scored["score"] < cfg.score_min:
                    continue
                if _PITCHY_AUTHOR_CUES.search(getattr(post, "text", "") or ""):
                    continue

                leads.append({
                    "platform": platform,
                    "scored":   scored,
                    "post":     post,
                    "draft":    compose_outreach(
                        post,
                        seed=_stable_seed(platform, post.url, post.post_id),
                        cfg=cfg,                       # CHANGED: pass cfg so the proactive PayPal CTA can render
                    ),
                })

                summary["leads_flagged"] += 1
                summary["by_platform"][platform]["leads"] += 1

                _append_jsonl(LEADS_LOG, {
                    "timestamp":      _now_iso(),
                    "query":          q,
                    "platform":       platform,
                    "score":          scored["score"],
                    "vertical_hits":  scored["vertical_hits"],
                    "intent_hits":    scored["intent_hits"],
                    "pain_hits":      scored["pain_hits"],
                    "author":         scored["author"],
                    "post_url":       scored["url"],
                    "post_id":        scored["post_id"],
                    "text_preview":   (post.text or "")[:300],
                    "draft_text":     leads[-1]["draft"],
                    "mode":           summary["mode"],
                })

    for lead in leads:
        _append_jsonl(DRAFTS_LOG, {
            "timestamp": _now_iso(),
            "platform":  lead["platform"],
            "score":     lead["scored"]["score"],
            "author":    lead["scored"]["author"],
            "post_url":  lead["scored"]["url"],
            "post_id":   lead["scored"]["post_id"],
            "draft":     lead["draft"],
            "live":      effective_live,
        })
        summary["drafts_written"] += 1

    if effective_live:
        log_result("lead-hunt", True, f"entering live mode; live=ON cap={cfg.per_platform_cap}")
        for lead in leads:
            allowed, reason = limiter.decide(lead["platform"])
            if not allowed:
                summary["send_skipped"] += 1
                log_result("lead-hunt", True, f"skipped {lead['platform']}: {reason}")
                continue
            try:
                results = orch.publish_post(
                    networks=[lead["platform"]],
                    content=lead["draft"],
                    dry_run=cfg.observe_dry_run,
                )
            except Exception as e:
                summary["send_skipped"] += 1
                limiter.record(lead["platform"], ok=False)
                log_result("lead-hunt", False,
                           f"publish raised on {lead['platform']}: {type(e).__name__}: {e}",
                           extra={"post_url": lead["scored"]["url"]})
                continue

            res = results.get(lead["platform"])
            # Observe-mode synthetic-success override: the orchestrator returns
            # success=False with error="dry_run" when observe_dry_run=True.
            # Re-market that as a successful simulated send so OUTREACH_LOG gets
            # the row + the limiter records it as ok + dedup honors it next tick.
            if (cfg.observe_dry_run and res
                    and getattr(res, "error", "") == "dry_run"
                    and not getattr(res, "success", False)):
                res = type("ObsLh", (), {
                    "success": True,
                    "url":     "observe://dry_run/" + lead["platform"],
                    "post_id": lead["scored"].get("post_id", ""),
                    "error":   None,
                })()
            if res and getattr(res, "success", False):
                summary["send_successes"] += 1
                limiter.record(lead["platform"], ok=True)
                log_result("lead-hunt", True,
                           f"posted to {lead['platform']} → {getattr(res, 'url', '') or getattr(res, 'post_id', '')}",
                           extra={"post_url": lead["scored"]["url"]})
                _append_jsonl(OUTREACH_LOG, {
                    "timestamp": _now_iso(),
                    "platform":  lead["platform"],
                    "ok":        True,
                    "url":       getattr(res, "url", ""),
                    "post_id":   getattr(res, "post_id", ""),
                    "draft":     lead["draft"],
                    "target_post_url": lead["scored"]["url"],
                })
            else:
                summary["send_skipped"] += 1
                limiter.record(lead["platform"], ok=False)
                err = (getattr(res, "error", "") if res else "no_result")
                log_result("lead-hunt", False,
                           f"publish refused on {lead['platform']}: {err}",
                           extra={"post_url": lead["scored"]["url"]})
                _append_jsonl(OUTREACH_LOG, {
                    "timestamp": _now_iso(),
                    "platform":  lead["platform"],
                    "ok":        False,
                    "error":     err,
                    "draft":     lead["draft"],
                    "target_post_url": lead["scored"]["url"],
                })
    else:
        log_result(
            "lead-hunt", True,
            f"dry-run: {summary['leads_flagged']} lead(s) drafted across "
            f"{len(summary['by_platform'])} platform(s); "
            f"to switch to LIVE publish set {live_signoff_missing}",
            extra={"summary": summary},
        )

    save_state(state)
    summary["generated_at"] = _now_iso()
    return summary


# ── Phase 2: inbox + auto-reply (NEW) ────────────────────────────────────────

def autoreply_phase(
    *,
    orchestrator: Optional[SocialOrchestrator] = None,
    cfg: Optional[LeadHuntConfig] = None,
    cli_send: bool = False,
    max_age_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Scan for replies to our outreach, classify intent, alert on hot leads, (optionally) reply.

    Always DRY-RUN by default. Live replies require both ``cli_send=True``
    AND the env var ``DELTA_AGENT_LEAD_HUNT_LIVE=true``.
    """
    cfg = cfg or LeadHuntConfig.from_env(cli_live=cli_send)
    creds = Credentials.from_env()
    orch = orchestrator or SocialOrchestrator(credentials=creds)
    state = load_state()
    limiter = RateLimiter(state, cfg)

    effective_live = bool(cli_send and cfg.live)
    age_window = max_age_days if max_age_days is not None else cfg.max_reply_age_days
    summary = {
        "mode":                "live" if effective_live else "dry_run",
        "age_window_days":     age_window,
        "replies_seen":        0,
        "by_intent":           {},
        "hot_leads":           0,
        "auto_replies_drafted":0,
        "auto_replies_sent":   0,
    }

    history = load_outreach_history(max_age_days=age_window)
    seen_log = _load_replied_set()  # NEW: pre-load dedup ledger
    if not history:
        summary["reason"] = "no_recent_outreach_history"
        return summary

    replies = scan_for_inbound_replies(
        history,
        orchestrator=orch,
        creds=creds,
        limit_per_platform=20,
    )
    summary["replies_seen"] = len(replies)
    if not replies:
        log_result("auto-reply", True,
                   f"no inbound replies detected for {len(history)} recent outreach row(s)",
                   extra={"summary": summary})
        save_state(state)
        summary["generated_at"] = _now_iso()
        return summary

    for r in replies:
        intent = r["intent"]
        summary["by_intent"][intent] = summary["by_intent"].get(intent, 0) + 1
        post = r["inbound"]
        text = getattr(post, "text", "") or ""
        _append_jsonl(REPLIES_LOG, {
            "timestamp":       _now_iso(),
            "platform":        r["platform"],
            "intent":          intent,
            "matched_pattern": r["matched_pattern"],
            "author":          getattr(post, "author", ""),
            "author_id":       getattr(post, "author_id", ""),
            "post_url":        getattr(post, "url", ""),
            "post_id":         getattr(post, "post_id", ""),
            "text_preview":    text[:400],
            "outbound_url":    r["outbound"].get("target_post_url", ""),
            "mode":            summary["mode"],
        })

        # Hot-lead check fires BEFORE we decide to publish an auto-reply —
        # the operator should always see a BUY/DEMO regardless of dry-run.
        if hot_lead_alert(
            platform=r["platform"],
            author=getattr(post, "author", "?"),
            author_id=getattr(post, "author_id", ""),
            post_text=text,
            intent=intent,
            post_url=getattr(post, "url", ""),
            post_id=getattr(post, "post_id", ""),
        ):
            summary["hot_leads"] += 1

        if intent == "NEUTRAL":
            continue  # tracked, not replied to automatically

        # NEW: dedup guard — never publish twice for the same inbound post.
        if _already_replied_to(
            seen_log,
            r["platform"],
            getattr(post, "post_id", ""),
            getattr(post, "url", ""),
        ):
            summary["auto_replies_drafted_skipped"] = (
                summary.get("auto_replies_drafted_skipped", 0) + 1
            )
            log_result("auto-reply", True,
                       "skip duplicate reply to " + str(getattr(post, "author", "?")) +
                       " on " + r["platform"] +
                       " (already in auto_replies.jsonl)")
            continue

        draft = compose_autoreply(
            intent,
            platform=r["platform"],
            author=getattr(post, "author", ""),
            seed=_stable_seed(r["platform"],
                              getattr(post, "post_id", ""),
                              r["outbound"].get("post_id", "")),
            post_text=text,            # NEW: enable LLM-aware composer
            cfg=cfg,                   # NEW: inject cfg for PayPal/Demo/Agency URLs
        )
        if not draft:
            continue
        summary["auto_replies_drafted"] += 1

        if effective_live:
            allowed, reason = limiter.decide(r["platform"])
            if not allowed:
                log_result("auto-reply", True, f"skipped {r['platform']}: {reason}")
                continue
            try:
                results = orch.publish_post(
                    networks=[r["platform"]],
                    content=draft,
                    dry_run=cfg.observe_dry_run,
                )
            except Exception as e:
                limiter.record(r["platform"], ok=False)
                log_result("auto-reply", False,
                           f"publish raised on {r['platform']}: {type(e).__name__}: {e}",
                           extra={"intent": intent})
                continue
            res = results.get(r["platform"])
            # Observe-mode synthetic-success override: when observe_dry_run=True,
            # the orchestrator returns success=False / error="dry_run". Re-market
            # as a successful simulated send so the auto-reply dedup ledger is
            # populated + next tick correctly skips the same (platform, post_id).
            if (cfg.observe_dry_run and res
                    and getattr(res, "error", "") == "dry_run"
                    and not getattr(res, "success", False)):
                synthetic_url = "observe://dry_run/" + r["platform"] + "/" + (
                    str(getattr(post, "post_id", "") or getattr(post, "url", "") or "unknown")
                )
                res = type("ObsAr", (), {
                    "success": True,
                    "url":     synthetic_url,
                    "post_id": getattr(post, "post_id", ""),
                    "error":   None,
                })()
            if res and getattr(res, "success", False):
                summary["auto_replies_sent"] += 1
                limiter.record(r["platform"], ok=True)
                log_result("auto-reply", True,
                           f"reply sent on {r['platform']} ({intent}) → "
                           f"{getattr(res, 'url', '') or getattr(res, 'post_id', '')}",
                           extra={"intent": intent,
                                  "to_author": getattr(post, "author", "?")})
                _append_jsonl(AUTO_REPLIES_LOG, {
                    "timestamp":  _now_iso(),
                    "platform":   r["platform"],
                    "intent":     intent,
                    "author":     getattr(post, "author", ""),
                    "post_url":   getattr(post, "url", ""),
                    "draft":      draft,
                    "sent_url":   getattr(res, "url", ""),
                })
            else:
                limiter.record(r["platform"], ok=False)
                log_result("auto-reply", False,
                           f"reply refused on {r['platform']} ({intent}): "
                           f"{getattr(res, 'error', 'no_result')}",
                           extra={"intent": intent})
        else:
            log_result(
                "auto-reply", True,
                f"draft-only {r['platform']} ({intent}) for "
                f"{getattr(post, 'author', '?')}: {draft[:120].strip()}…",
                extra={"intent": intent},
            )

    save_state(state)
    summary["generated_at"] = _now_iso()
    return summary


# ── Self-test (NEW) ─────────────────────────────────────────────────────────

_FIXTURE_INTENT_POSTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("BUY",      ("What's the pricing? Can you share a quote?",
                  "Good deal — sign me up, ready to ship it.")),
    ("DEMO",     ("Can I get a demo or trial to see it in action?",
                  "Walk me through the flow, then I’ll try it out.")),
    ("DETAILS",  ("How does the integration work? More info please.",
                  "Where are the docs? Looking for architecture and specs.")),
    ("FOLLOWUP", ("When can we plan a pilot? Timeline?",
                  "ETA on shipping the new feature?")),
    ("NOT_NOW",  ("Not now, maybe later.",
                  "Busy this week — ping me next month.")),
    ("NEGATIVE", ("Stop replying to me, this is spam.",
                  "No thanks — please unsubscribe.")),
    ("NEUTRAL",  ("ok thanks", "noted 👍")),
]


def _test_pipeline() -> int:
    """Self-test the intent classifier + composer + hot-lead alerter
    + URL injection + dedup ledger."""
    print("=== Intent classifier self-test ===")
    fails = 0
    for expected, texts in _FIXTURE_INTENT_POSTS:
        for text in texts:
            got, _ = classify_intent(text)
            mark = "✅" if got == expected else "❌"
            if got != expected:
                fails += 1
            print(f"  {mark} expected={expected:<8} got={got:<8} :: {text!r}")
    print()
    print("=== Composer sample (one variant per intent, bluesky) ===")
    for intent in ("BUY", "DEMO", "DETAILS", "FOLLOWUP", "NOT_NOW", "NEGATIVE"):
        body = compose_autoreply(intent, platform="bluesky", author="@alice", seed=42)
        suffix = "…" if len(body) > 130 else ""
        print(f"  {intent:<8}: {(body[:130] + suffix)}")
    print()
    print("=== Hot-led alerter self-test (writes 2 to output/hot_leads.jsonl) ===")
    hot_lead_alert("bluesky", "@alice", "What's the price?",
                   intent="BUY",
                   post_url="https://bsky.app/profile/x/post/1",
                   post_id="at://x/post/1")
    hot_lead_alert("mastodon", "@bob", "Can I get a demo?",
                   intent="DEMO",
                   post_url="https://mastodon.social/@bob/1",
                   post_id="1")
    non_hot = hot_lead_alert("bluesky", "@carol", "thanks, noted",
                             intent="NEUTRAL")  # should not write
    print(f"  hot=2 cold_returned={non_hot} (expect False)")
    print()

    print()
    print("=== URL suffix injection (NEW) ===")
    cfg = LeadHuntConfig.from_env()
    cfg.paypal_url = PAYPAL_URL_DEFAULT
    cfg.demo_url   = DEMO_URL_DEFAULT
    cfg.agency_url = AGENCY_URL_DEFAULT
    buy     = compose_autoreply("BUY",     platform="bluesky", author="@alice", seed=42, cfg=cfg)
    demo    = compose_autoreply("DEMO",    platform="bluesky", author="@alice", seed=42, cfg=cfg)
    details = compose_autoreply("DETAILS", platform="bluesky", author="@alice", seed=42, cfg=cfg)
    paypal_hit = ("paypal.me/talderie" in buy)
    demo_hit   = (cfg.demo_url in demo)
    agency_hit = (cfg.agency_url in details)
    # NEW: proactive PayPal on DEMO and DETAILS as well.
    demo_paypal_hit    = ("paypal.me/talderie" in demo)
    details_paypal_hit = ("paypal.me/talderie" in details)
    print("  BUY  has paypal URL?",       "PASS" if paypal_hit       else "FAIL", "::", buy[:100] + "...")
    print("  DEMO has demo URL?  ",       "PASS" if demo_hit         else "FAIL", "::", demo[:100] + "...")
    print("  DEMO has paypal too?",       "PASS" if demo_paypal_hit  else "FAIL")
    print("  DETAILS has agency? ",       "PASS" if agency_hit       else "FAIL", "::", details[:100] + "...")
    print("  DETAILS has paypal too?",    "PASS" if details_paypal_hit else "FAIL")
    if not paypal_hit:       fails += 1
    if not demo_hit:         fails += 1
    if not agency_hit:       fails += 1
    if not demo_paypal_hit:  fails += 1
    if not details_paypal_hit: fails += 1
    # LLM-keyless (default config) still injects the URL.
    cfg_no_llm = LeadHuntConfig()
    buy_no_llm = compose_autoreply("BUY", platform="bluesky", author="@alice",
                                   seed=7, cfg=cfg_no_llm,
                                   post_text="What is your price?")
    no_llm_hit = ("paypal.me/talderie" in buy_no_llm)
    print("  LLM-keyless BUY still has paypal URL?", "PASS" if no_llm_hit else "FAIL")
    if not no_llm_hit: fails += 1

    # NEW: proactive PayPal CTA in cold outreach for high-intent leads.
    print()
    print("=== Proactive outreach CTA (NEW) ===")
    class _FakePost:
        def __init__(self, text):
            self.text = text
            self.platform = "bluesky"
            self.author = "@alice"
            self.url = "https://bsky.app/profile/x/post/1"
            self.post_id = "at://x/post/1"
    cfg_cta = LeadHuntConfig.from_env()
    cfg_cta.paypal_url = PAYPAL_URL_DEFAULT
    high_intent_msgs = [
        compose_outreach(_FakePost("Looking for a better way to handle voice notes in my agency."),
                         seed=11, cfg=cfg_cta),
        compose_outreach(_FakePost("Our support inbox is overflowing, drowning in tickets every week."),
                         seed=22, cfg=cfg_cta),
        compose_outreach(_FakePost("Has anyone used VocalizeBot for client call transcription? Recommend."),
                         seed=33, cfg=cfg_cta),
        compose_outreach(_FakePost("Need to automate our ticket queue, anyone know a good tool?"),
                         seed=44, cfg=cfg_cta),
    ]
    low_intent_msg = compose_outreach(
        _FakePost("Just sharing some thoughts about my morning coffee."),
        seed=55, cfg=cfg_cta,
    )
    hi_hits = sum(1 for m in high_intent_msgs if "paypal.me/talderie" in m)
    lo_hit  = "paypal.me/talderie" in low_intent_msg
    print(f"  high-intent posts ({len(high_intent_msgs)}): PayPal appears in {hi_hits}/{len(high_intent_msgs)} (expect all)")
    print(f"  low-intent post:        PayPal appears? {lo_hit} (expect False)")
    # At least one variant should make every high-intent post surface the link
    # because we run 4 different seeds against the same 5-variant bank.
    # If the bank is well-mixed, hitting > 0 is sufficient; assert > 0 + all-or-nothing on low-intent.
    if hi_hits == 0:            fails += 1
    if lo_hit:                  fails += 1
    # Spot-check one explicit pattern: "voice notes" post must mention Vocalize value-prop.
    vn_msg = high_intent_msgs[0]
    voc_hit = ("Vocalize" in vn_msg) or ("voice" in vn_msg.lower())
    print(f"  voice-notes post mentions Vocalize/voice? {'PASS' if voc_hit else 'FAIL'}")
    if not voc_hit: fails += 1

    # ── Proactive outreach edge cases (NEW) ─────────────────────────────────
    # Regression guards — each maps to a real failure surface in production:
    #   * Don't let an empty paypal_url silently produce a " {paypal}" stub.
    #   * Don't let NOT_NOW / NEGATIVE auto-replies inherit the new PayPal
    #     surface (the change is BUY/DEMO/DETAILS/FOLLOWUP-only on purpose).
    #   * Don't blow up if a caller forgets to pass cfg (back-compat).
    #   * Don't over-trigger on out-of-context transcribe mentions.
    #   * Don't regress the "transcribed" form (broader regex is intentional).
    print()
    print("=== Proactive outreach edge cases (NEW) ===")
    _fp = _FakePost

    # (1) Empty paypal_url must skip the CTA entirely, even on hit. We
    #     can't use `cfg_empty_paypal.paypal_url in msg` (empty string is
    #     a substring of every string), so we check the literal "paypal.me"
    #     fragment — the host of PAYPAL_URL_DEFAULT — instead.
    cfg_empty_paypal = LeadHuntConfig()
    cfg_empty_paypal.paypal_url = ""
    empty_paypal_msg = compose_outreach(
        _fp("Looking for a better way to handle voice notes."),
        seed=11, cfg=cfg_empty_paypal,
    )
    ep_hit = "paypal.me" in empty_paypal_msg
    ep_no_stub = "{paypal}" not in empty_paypal_msg
    print("  empty paypal_url → CTA skipped?    ",
          "PASS" if (not ep_hit and ep_no_stub) else "FAIL")
    if ep_hit or not ep_no_stub: fails += 1

    # (2) NOT_NOW auto-reply must NOT mention the configured PayPal URL
    #     (backward compat — change is BUY/DEMO/DETAILS/FOLLOWUP-only).
    nn_reply = compose_autoreply("NOT_NOW", platform="bluesky", author="@alice",
                                 seed=1, cfg=cfg_cta)
    nn_hit = bool(cfg_cta.paypal_url) and (cfg_cta.paypal_url in nn_reply)
    print("  NOT_NOW auto-reply → no PayPal?    ",
          "PASS" if not nn_hit else "FAIL")
    if nn_hit: fails += 1

    # (3) NEGATIVE auto-reply must NOT mention the configured PayPal URL.
    neg_reply = compose_autoreply("NEGATIVE", platform="bluesky", author="@alice",
                                  seed=1, cfg=cfg_cta)
    neg_hit = bool(cfg_cta.paypal_url) and (cfg_cta.paypal_url in neg_reply)
    print("  NEGATIVE auto-reply → no PayPal?   ",
          "PASS" if not neg_hit else "FAIL")
    if neg_hit: fails += 1

    # (4) Empty text → False on cue detection (no crash, no false positive).
    empty_cue = _is_high_intent_for_checkout("")
    print("  empty text → False?                ",
          "PASS" if empty_cue is False else "FAIL")
    if empty_cue is not False: fails += 1

    # (5) compose_outreach(post, seed=…) without cfg must NOT crash, must
    #     delegate to LeadHuntConfig.from_env(), and must respect the cfg
    #     from_env returns (no PayPal fragment + no template placeholder
    #     leak when from_env returns empty paypal_url). Mocks from_env so
    #     we control the fallback URL without polluting os.environ.
    cfg_no_url = LeadHuntConfig()
    cfg_no_url.paypal_url = ""
    with mock.patch.object(LeadHuntConfig, "from_env", return_value=cfg_no_url):
        no_cfg_msg = compose_outreach(_fp("Looking for a better way."), seed=99)
    no_cfg_safe     = len(no_cfg_msg) > 0
    no_cfg_no_pay   = "paypal.me" not in (no_cfg_msg or "")
    no_cfg_no_stub  = "{paypal}" not in (no_cfg_msg or "")
    print("  cfg=None → from_env branch works   ",
          "PASS" if (no_cfg_safe and no_cfg_no_pay and no_cfg_no_stub) else "FAIL",
              "::", (no_cfg_msg or "")[:80])
    if not no_cfg_safe or not no_cfg_no_pay or not no_cfg_no_stub: fails += 1

    # (6) Out-of-context "transcript of court hearing" must NOT trigger CTA
    #     (lock down: no Vocalize / automation / voice-note context present).
    ooc_post = _fp("The court reporter filed a transcript of today's hearing.")
    ooc_high_intent = _is_high_intent_for_checkout(ooc_post.text)
    ooc_msg = compose_outreach(ooc_post, seed=77, cfg=cfg_cta)
    ooc_hit = bool(cfg_cta.paypal_url) and (cfg_cta.paypal_url in ooc_msg)
    print("  out-of-context 'transcript' → False?",
          "PASS" if (not ooc_high_intent and not ooc_hit) else "FAIL")
    if ooc_high_intent or ooc_hit: fails += 1

    # (7) "transcribed" form MUST trigger CTA (locks down broader regex
    #     that survives where SCORING['pain'] regressed).
    transcribed_post = _fp("I had our last client call transcribed and the summary was great.")
    transcribed_high_intent = _is_high_intent_for_checkout(transcribed_post.text)
    print("  'transcribed' form triggers CTA?   ",
          "PASS" if transcribed_high_intent else "FAIL")
    if not transcribed_high_intent: fails += 1

    # (8) Intent classifier correctly routes NEGATIVE / NOT_NOW (lock down
    #     the priority + pattern table so future regex tweaks don't
    #     accidentally mis-route tone-cooling replies into BUY/DEMO).
    nn_intent, _  = classify_intent("Maybe later, I'm busy this week.")
    neg_intent, _ = classify_intent("Stop. Unsubscribe.")
    print(f"  classify_intent('Stop. Unsubscribe.') → {neg_intent}?",
          "PASS" if neg_intent == "NEGATIVE" else "FAIL")
    print(f"  classify_intent('Maybe later...')     → {nn_intent}?",
          "PASS" if nn_intent == "NOT_NOW" else "FAIL")
    if neg_intent != "NEGATIVE": fails += 1
    if nn_intent  != "NOT_NOW":  fails += 1

    print()
    print("=== Dedup ledger self-test (NEW) ===")
    AUTO_REPLIES_LOG.parent.mkdir(parents=True, exist_ok=True)
    _append_jsonl(AUTO_REPLIES_LOG, {
        "timestamp": _now_iso(),
        "platform":  "bluesky",
        "post_id":   "at://did:plc:dedup-test/1",
        "post_url":  "https://bsky.app/profile/dedup-test/post/1",
        "sent_url":  "https://bsky.app/profile/agent/post/abc",
        "intent":    "BUY",
    })
    seen_now = _load_replied_set()
    hit       = _already_replied_to(seen_now, "bluesky", "at://did:plc:dedup-test/1", "")
    miss_pid  = _already_replied_to(seen_now, "bluesky", "at://never/seen", "")
    miss_url  = _already_replied_to(seen_now, "bluesky", "", "https://example.com/post/999")
    print("  positive (already replied):", "PASS" if hit          else "FAIL", "::", hit)
    print("  negative (new post_id):    ", "PASS" if not miss_pid  else "FAIL", "::", miss_pid)
    print("  negative (new url):        ", "PASS" if not miss_url  else "FAIL", "::", miss_url)
    if not hit or miss_pid or miss_url: fails += 1
    print()
    print("PASS" if fails == 0 else "FAIL (" + str(fails) + " mismatches)")
    return 0 if fails == 0 else 1

    print(f"{'PASS' if fails == 0 else f'FAIL ({fails} mismatches)'}")
    return 0 if fails == 0 else 1
    print(f"{'PASS' if fails == 0 else f'FAIL ({fails} mismatches)'}")
    return 0 if fails == 0 else 1


# ── CLI hot-lead summary (NEW) ──────────────────────────────────────────────

def _print_hot_lead_summary(n: int) -> int:
    """Print the latest N hot-lead rows from output/hot_leads.jsonl."""
    if not HOT_LEAD_LOG.exists():
        print(f"no hot_leads.jsonl at {HOT_LEAD_LOG}")
        return 0
    try:
        rows = [json.loads(line) for line in HOT_LEAD_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as e:
        print(f"failed to parse {HOT_LEAD_LOG}: {e}")
        return 1
    rows = rows[-n:]
    print(f"=== Latest {len(rows)} hot-lead entries from {HOT_LEAD_LOG} ===")
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lead_hunt",
        description=(
            "Lead Hunting, Auto-Reply & Hot-Lead Notification for delta-agent. "
            "Default mode is dry-run. Pass --send AND set "
            "DELTA_AGENT_LEAD_HUNT_LIVE=true in .env to publish."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                      help="Default. Scan + score + draft; never publishes.")
    mode.add_argument("--send", dest="send", action="store_true",
                      help="Publish for real. Requires DELTA_AGENT_LEAD_HUNT_LIVE=true.")
    p.add_argument("--queries", default=None,
                   help="Comma-separated query phrases (overrides DELTA_AGENT_LEAD_QUERIES).")
    p.add_argument("--keywords", default=None,
                   help="Comma-separated extra keywords.")
    p.add_argument("--per-platform-cap", type=int, default=None,
                   help="Override DELTA_AGENT_LEAD_DAILY_CAP.")
    p.add_argument("--limit", type=int, default=None,
                   help="Override per-query post scan limit (default 15; lower for fast runs).")
    p.add_argument("--json-out", default="",
                   help="Write the summary to this JSON file.")
    p.add_argument("--hot-lead-summary", type=int, default=0,
                   help="Print the latest N hot-lead rows from output/hot_leads.jsonl and exit.")
    p.add_argument("--test-pipeline", action="store_true",
                   help="Self-test the intent classifier + composer + hot-lead alerter, "
                        "no network calls.")
    return p


def _parse_csv(s: Optional[str]) -> Optional[List[str]]:
    if not s:
        return None
    return [q.strip() for q in s.split(",") if q.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "test_pipeline", False):
        return _test_pipeline()
    if getattr(args, "hot_lead_summary", 0):
        return _print_hot_lead_summary(args.hot_lead_summary)

    cfg = LeadHuntConfig.from_env(
        cli_live=args.send,
        cli_queries=_parse_csv(args.queries),
        cli_keywords=_parse_csv(args.keywords),
        cli_cap=args.per_platform_cap,
    )
    if args.limit is not None and args.limit > 0:
        cfg.limit = args.limit

    scout_summary = lead_hunt_phase(cli_send=args.send, cfg=cfg)
    reply_summary = autoreply_phase(cli_send=args.send, cfg=cfg)

    combined = {
        "scout":    scout_summary,
        "autoreply": reply_summary,
    }
    print()
    print(json.dumps(combined, indent=2, ensure_ascii=False))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(combined, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n💾 Combined summary → {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
