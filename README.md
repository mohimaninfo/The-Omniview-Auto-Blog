# 🤖 Autonomous Blogger

**A fully autonomous, 24/7 self-running blog powered by a 10-agent AI content pipeline — at $0/month.**

Built on Google Blogger (free hosting), Gemini 2.5 Flash (free tier), GitHub Actions (free CI/CD), Firebase (free Spark plan), and Disqus (free comments). Zero human involvement after initial setup.

---

## Architecture Overview

```
GitHub Actions (cron scheduler)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                AGENT 1: ORCHESTRATOR                │
│  Reads taxonomy.json → decides genre/topic/layer   │
│  Manages daily schedule + assembles final post      │
└──────────────┬──────────────────────────────────────┘
               │ task packet
    ┌──────────┴──────────────────────────┐
    ▼                                     ▼
AGENT 2                              AGENT 3
Topic Discovery                      Research
(Google Trends RSS                   (Gemini 2.5 Flash
 + Reddit RSS                         + web grounding)
 + dedup check)                      Research Brief ──►
    │                                     │
    └──────────────────┬──────────────────┘
                       ▼
                  AGENT 4: Content Generation
                  (Gemini 2.5 Flash + layer template)
                       │
         ┌─────────────┼─────────────────────┐
         ▼             ▼                     ▼
    AGENT 5       AGENT 6              AGENT 7+8
    Citations      SEO                 Image + Video
    (validate      (meta, schema,       (Wikimedia,
     URLs →         labels, links)      Unsplash,
     Wayback)                           YouTube)
         └─────────────┬─────────────────────┘
                       ▼
                  AGENT 9: Publisher
                  (Blogger API v3 → publish)
                  (GitHub logs update)
                       │
              [weekly/monthly]
                       ▼
                  AGENT 10: Self-Improvement
                  (analyse performance → update taxonomy)
```

---

## Feature Summary

### Content Pipeline
- **10 specialized AI agents**, each with a single responsibility
- **Multi-genre taxonomy**: 10 genres × 5 topics × 9 layer types
- **Anti-hallucination**: every factual claim requires a cited, validated source URL
- **Deduplication**: compares new topics against all published post titles
- **Self-evolution**: weekly trends analysis expands genres/topics automatically

### User Features (on Blogger)
- 🔐 **Login** via Google OAuth (native Blogger) or Disqus SSO
- 💬 **Comments** via Disqus (threaded, spam-filtered, upvotes)
- ❤️ **Likes** via Firebase Realtime Database (per-user, no duplicates)
- 🔗 **Share buttons**: Twitter/X, Facebook, LinkedIn, WhatsApp, Telegram, Reddit, Email, Copy
- 📖 **Rich navigation**: mega menu, breadcrumbs, content-type badges, sidebar filters

### Technical Stack (all free)
| Layer | Service | Cost |
|---|---|---|
| Hosting | Google Blogger | $0 |
| AI | Gemini 2.5/1.5 Flash | $0 |
| Automation | GitHub Actions | $0 |
| Reactions | Firebase Realtime DB | $0 |
| Comments | Disqus | $0 |
| Images | Wikimedia / Unsplash / Pollinations.ai | $0 |
| Video | YouTube Data API | $0 |
| **Total** | | **$0/month** |

---

## Repository Structure

```
autonomous-blogger/
├── .github/
│   └── workflows/
│       ├── daily_pipeline.yml          # Main daily content pipeline
│       ├── weekly_improvement.yml      # Self-improvement agent
│       └── monthly_expansion.yml       # Genre expansion agent
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py                 # Agent 1: Orchestrator
│   ├── topic_discovery.py              # Agent 2: Topic Discovery
│   ├── research.py                     # Agent 3: Research
│   ├── content_generation.py           # Agent 4: Content Generation
│   ├── reference_citation.py           # Agent 5: Reference & Citation
│   ├── seo.py                          # Agent 6: SEO
│   ├── image_agent.py                  # Agent 7: Image
│   ├── video_agent.py                  # Agent 8: Video
│   ├── publisher.py                    # Agent 9: Publisher
│   └── self_improvement.py             # Agent 10: Self-Improvement
│
├── config/
│   ├── settings.py                     # Central config loader
│   ├── tone_profiles.json              # Genre tone profiles
│   ├── section_templates.json          # Layer section templates
│   └── quota_state.json                # Runtime quota tracker (gitignored)
│
├── taxonomy/
│   ├── taxonomy.json                   # Full genre/topic/layer taxonomy
│   └── taxonomy_changelog.json         # Version history of taxonomy changes
│
├── prompts/
│   ├── news_prompt.txt
│   ├── research_prompt.txt
│   ├── howto_prompt.txt
│   ├── opinion_prompt.txt
│   ├── casestudy_prompt.txt
│   ├── interview_prompt.txt
│   ├── listicle_prompt.txt
│   ├── review_prompt.txt
│   ├── explainer_prompt.txt
│   └── video_decision_prompt.txt
│
├── templates/
│   ├── blogger_template.xml            # Full Blogger XML theme
│   ├── post_html_template.html         # HTML shell for assembled posts
│   └── genre_landing_page.html         # Auto-generated genre landing page
│
├── logs/
│   ├── published_posts.json            # Post log (URL, metadata, date)
│   ├── quota_log.json                  # Daily API usage log
│   └── pipeline_runs.json             # Run history
│
├── utils/
│   ├── gemini_client.py                # Gemini API wrapper + rate limiting
│   ├── blogger_client.py               # Blogger API v3 wrapper
│   ├── firebase_client.py              # Firebase Admin SDK wrapper
│   ├── link_validator.py               # HTTP HEAD checker + archive fallback
│   ├── dedup_checker.py                # Duplicate post detection
│   ├── rss_fetcher.py                  # Google Trends + Reddit RSS
│   └── quota_manager.py               # Quota tracker + backoff logic
│
├── tests/
│   ├── test_agents.py
│   ├── test_utils.py
│   └── fixtures/
│       └── sample_research_brief.json
│
├── docs/
│   ├── DEPLOYMENT_CHECKLIST.md        # [M] Step-by-step setup guide
│   ├── BLOGGER_SETUP.md               # [F] Blogger API + OAuth guide
│   ├── FIREBASE_SETUP.md              # [H] Firebase like counter guide
│   └── DISQUS_SETUP.md                # [I] Disqus comment system guide
│
├── sample_output/
│   └── sample_post.html               # [N] Full sample post output
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```


---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/autonomous-blogger.git
cd autonomous-blogger

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# → Fill in all values (see docs/DEPLOYMENT_CHECKLIST.md)

# 4. Test locally (dry run)
DRY_RUN=true python3 -m agents.orchestrator --run-once

# 5. Run tests
pytest tests/ -v

# 6. Deploy
git push origin main
# → GitHub Actions takes over automatically
```

Full setup: see **[docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md)**

---

## Configuration

All configuration lives in:
- **`.env`** — secrets & API keys (never commit)
- **`taxonomy/taxonomy.json`** — content strategy (genres, topics, layers)
- **`config/tone_profiles.json`** — per-genre writing style
- **`config/section_templates.json`** — per-layer content structure

---

## Quota & Rate Limits

The `QuotaManager` (`utils/quota_manager.py`) handles everything automatically:

- Tracks daily Gemini API usage in `config/quota_state.json`
- Enforces RPM limit (15 req/min on free tier)
- Exponential backoff with jitter on transient failures
- Auto-switches from Gemini 2.5 Flash → 1.5 Flash on quota exhaustion
- Priority queue: Publisher/Orchestrator (critical) always get quota before lower-priority agents

---

## Monitoring

- **GitHub Actions** job logs: visible in the Actions tab per run
- **`logs/published_posts.json`**: all published post metadata
- **`logs/quota_log.json`**: daily API usage history
- **`logs/pipeline_runs.json`**: run success/failure history
- **Agent 10** (Self-Improvement): posts a performance summary to the Actions job summary weekly

---

## License

MIT — free to use, modify, and deploy.

---

## Contributing

Issues and PRs welcome. This project is intentionally designed to run at $0 cost —
please flag any changes that introduce paid dependencies.
