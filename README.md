# QuizForge: exam preparation built from your syllabus

QuizForge is a white-label platform for institutions that prepare candidates for
competitive exams. It ships with two courses: **NRB Assistant Director (IT)**, with 3 papers, and **Lok Sewa Computer Officer**.

- **Admins** paste the official syllabus. The platform turns it into chapters and topics.
  For each topic it uses uploaded PDFs, or researches the web when there are none, and
  writes exam-style MCQs at three difficulty levels.
- **Students** practise topic by topic and sit full-length, timed mock tests with negative
  marking. A chapter-wise analysis afterwards shows where to focus.
- **Branding**: each institution sets its own name, colours, logo, tagline and sign-up
  policy from the admin panel, with no code changes.

## Features

| | |
|---|---|
| **Syllabus engine** | Paste an outline (`Chapter [weight]` / `- Topic: detail`). Merge or replace without losing existing content. Edit chapters, topics and weights inline. |
| **Content pipeline** | One click builds a course's question bank in the background, with live progress: uploaded PDFs → otherwise web research guided by the syllabus → questions at easy/medium/hard. |
| **Mock tests** | The paper is assembled by chapter weight, with unseen questions first. Server-enforced timer, autosave (safe to refresh), question palette, mark for review, auto-submit at zero, negative marking, pass mark. |
| **Results** | Score, pass/fail, marks lost to negative marking, chapter-wise analysis, and an answer review with explanations, filterable by wrong / skipped / marked. |
| **Practice** | Topic quizzes at a chosen difficulty, with instant explanations, history and a "needs practice" list. |
| **Admin** | Overview, live system health (shows whether each service is on cloud or local), course editor, PDF uploads, question bank review, users and roles, branding. |

## Where questions come from

Every question in the bank is labelled with its source:

| Source | How it gets in |
|---|---|
| **Study notes** | `scripts/import_notes.py --with-mcqs` copies the MCQs already written in the notes (answer key and explanations included). |
| **AI-written** | The AI writes new questions from the notes. Each syllabus unit's notes are stored as chapter-wide knowledge, so generation stays on-syllabus. When the notes are exhausted (new attempts keep producing duplicates), it researches the topic on the web and writes from that. |
| **Past papers** | *Admin → Course → Sources & past papers → Upload*. PDFs are read directly and scans or photos are OCR'd with Tesseract (English and Nepali). The AI extracts every MCQ, keeps the official answer when the paper gives one, explains it, and files it under the best-matching topic. |
| **Past papers found online** | *Admin → Course → Sources & past papers → Find past papers* searches **Lok Sewa Aayog** (the official question-bank API behind psc.gov.np, filtered by designation, e.g. कम्प्युटर अधिकृत / शाखा अधिकृत), **Nepal Rastra Bank** (its official नमूना प्रश्नपत्र archive) and the **web** (paper PDFs, scanned pages and listing pages, which it follows to the individual papers). Every paper appears in the list straight away with source, year, status and an *Open* link, then is downloaded and read: legacy-font Nepali PDFs (e.g. Preeti) and scans are OCR'd page by page. MCQs are extracted; subjective papers stay in the list as "Subjective / no MCQs". Students see the read papers under *Past papers* on the course page. |
| **Collected online** | *Collect old questions online* searches the web for previous-year and model questions of the exam. Many sites post papers as scanned images or PDFs, so those are downloaded and OCR'd. Only on-syllabus MCQs are kept, and each one records its source URL. |

**When the bank runs out during a mock test.** Before a paper is assembled, any
chapter where the student has too few unseen questions gets new ones, written by the AI
from the syllabus and notes. Cloud models go first; when they are rate-limited the local
model takes over. The student waits at most 45 seconds. Questions that finish later are
saved for the next paper, and the test is filled with the least-recently-seen questions.

**All papers in one sitting (NRB).** Choosing *All 3 papers together* gives one exam with
three sections (Paper I, II, III). There's a single timer for the combined time (3 × 30 min),
section tabs show each paper's progress and its 30-minute share, and questions never mix
across sections. Results are scored per paper.

**Marking always follows the syllabus.** Each course stores its official marking scheme:
marks per question, negative marking (as a fraction of the question's mark), the pass
mark, and the pass rule. NRB AD (IT) uses *pass mark in each paper* (40 in every paper);
Lok Sewa Computer Officer Paper I uses *pass mark on the combined total* (40 of 100). The
same scheme drives the instructions shown before the exam, the scoring and the results.

**Question grid.** The exam always shows every question number (1–100 for the full
Computer Officer paper): a side panel on desktop, a pinned scrolling strip on phones, plus
a "Go to #" box. Students can answer in any order.

**Freshness.** Practice quizzes and mock tests serve questions the student has never
seen first, then the ones seen longest ago. When a student runs short of unseen
questions, the AI writes new ones on the spot with the fast cloud models (Groq or Gemini,
about 5 s). If those are busy, a background top-up is queued and a few old questions
repeat in the meantime. Practice quizzes tell the student how many questions were
written for them and how many are repeats.

### Importing the NRB folder

```bash
venv/bin/python -m scripts.seed_nrb --reset                          # both courses from the official syllabi
venv/bin/python -m scripts.import_notes --notes-dir ~/Desktop/nrb    # notes as AI knowledge
venv/bin/python -m scripts.import_notes --notes-dir ~/Desktop/nrb --with-mcqs   # also copy the notes' MCQs
```

The syllabi live in `backend/scripts/syllabi/` as plain-text outlines:
- `nrb_ad_it.txt`: NRB Assistant Director (IT), 3 papers, each 25 MCQ / 30 min, with weights equal to the official MCQ count per unit.
- `lsc_computer_officer.txt`: Lok Sewa Computer Officer Paper I. Part I is general awareness and reasoning (50 MCQ) and Part II is IT (50 MCQ), for 100 MCQ in 90 minutes.

## Reliability: cloud first, local fallback

| Service | Primary | Automatic fallback |
|---|---|---|
| LLM | Groq `openai/gpt-oss-120b` → Gemini `gemini-flash-latest` | Ollama `mistral:7b` (local) |
| Vector DB | Qdrant Cloud (`QDRANT_URL`) | local Qdrant (`QDRANT_LOCAL_URL`) |
| Queue/cache | Redis Cloud (`REDIS_URL`) | local Redis (`REDIS_LOCAL_URL`) |
| Web research | Bing → Yandex → DuckDuckGo (via `ddgs`) | Wikipedia API |

When a provider is rate-limited, it is skipped for exactly as long as the provider asks
(per-minute limits) or for 15 minutes (daily quotas). The next provider is used in the
meantime. Qdrant and Redis are probed once when each process starts. The admin health
panel shows which one each service is using.

## Production hardening

- Passwords are hashed with bcrypt, must be at least 8 characters, and must mix letters
  and digits. Sessions use JWT bearer tokens.
- Sign-in is throttled after 8 failures in 15 minutes per IP and e-mail (tracked in Redis,
  or in memory if Redis is down).
- Generating questions (which costs API quota) is admin-only. Answers are scored on the
  server and are never sent to the browser before submission.
- Responses carry security headers (nosniff, frame-deny, referrer policy, plus HSTS in
  production) and a request id. Unexpected errors return a safe 500 that includes the
  request id, and the full error goes to the logs.
- Uploads must start with the PDF magic bytes, have a size limit, and get unique names on disk.
- With `APP_ENV=production`, the server refuses to start with a weak `JWT_SECRET` or
  localhost CORS, and the API docs are hidden.
- Production images: the API runs as a non-root user with several workers behind nginx.
  The SPA is served with gzip and long-term caching of hashed assets.

## Running in production

```bash
cp .env.example .env      # set APP_ENV=production, PUBLIC_URL, MYSQL_*, JWT_SECRET, API keys
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec ollama ollama pull mistral:7b      # local AI fallback, ~4 GB
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_nrb  # optional NRB course
```

Open `PUBLIC_URL` and register: **the first account becomes the administrator**. Put a
TLS-terminating proxy (Caddy, Traefik or a cloud load balancer) in front of port 80.

## Running for development

```bash
docker compose up -d mysql qdrant redis           # MySQL :3307, Qdrant :6333, Redis :6379
cd backend
python -m venv venv && venv/bin/pip install -r requirements-dev.txt
cp ../.env.example .env                           # localhost URLs; see comments inside
venv/bin/alembic upgrade head
venv/bin/python -m scripts.seed_nrb               # NRB Computer Officer course + syllabus
venv/bin/uvicorn app.main:app --reload --port 8000
venv/bin/celery -A app.workers.celery_app worker --loglevel=info --pool=solo    # second terminal
```

```bash
cd frontend
npm install
npm run dev               # http://localhost:5173 (proxies /api to :8000)
```

> **If `npm install` hangs** with no error, npm is probably stuck on an IPv6
> connection to the registry. Prefer IPv4 and add a fetch timeout:
> `NODE_OPTIONS=--dns-result-order=ipv4first npm install --fetch-timeout=30000`

## Tests

```bash
cd backend && venv/bin/python -m pytest -q
```

The 67 tests cover auth and roles, sign-in throttling, password policy, security headers,
the course tree, syllabus parsing/merging/replacing, uploads, ingestion, the content
pipeline, LLM output parsing, the cloud→local fallback and rate-limit cooldowns,
deduplication, practice quizzes, mock exams (paper by weight, resume, autosave,
negative marking, late submission, papers), freshness ordering and instant top-up, past-paper extraction and branding.

## Papers

A course can have several papers: write a `Paper I: …` or `Part II: …` line in the
syllabus outline. The exam question count and duration are set **per paper**. Students
can take a mock test of a single paper, or the full exam with all papers back to back.

## Project layout

| Path | Contents |
|---|---|
| `backend/app/routers/` | `auth`, `courses` (+ syllabus), `topics` (uploads, generation, practice), `quiz`, `exams` (mock tests, content pipeline, branding) |
| `backend/app/services/` | syllabus, exam, retrieval, generation (provider chain), web research, ingestion, embeddings, dedup, scoring |
| `backend/app/workers/` | Celery tasks `ingest_pdf`, `generate_questions`, `research_topic`, `build_course_bank` |
| `backend/app/infra.py` | cloud/local endpoint resolution |
| `backend/alembic/versions/` | migrations `0001` to `0004` |
| `frontend/src/pages/` | landing, auth, dashboard, courses, practice, mock tests, exam hall, results, `admin/*` |

## Roadmap to multi-tenant SaaS

The app currently runs one institution per deployment, branded through settings. The
path to one shared deployment serving many institutions:
1. Add an `organizations` table, an `org_id` on courses, users and settings, and
   scope every query by the signed-in user's organisation.
2. Resolve the organisation from the subdomain (`academy.quizforge.app`) for branding before login.
3. Add a super-admin console, per-organisation usage limits on AI generation, and billing.
4. Optionally keep a shared catalogue of master courses that institutions can subscribe to.
