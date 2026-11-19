# Hostel Maintenance Ticket Sorter

A console-based Python project that converts hostel complaints into maintenance work orders. It classifies issues, validates room numbers, raises safety urgency, routes work to teams, joins duplicate complaints, calculates due dates, and writes four reports.

## Features

- Reads `data/complaints.csv` and `data/open_tickets.csv`.
- Optional Gemini LLM classification (one API request per complaint).
- Offline fallback when no API key is configured.
- Validates room block A-D, floor 1-4, room 01-20, and checks that the room is written in the complaint.
- Python safety net can raise urgency but never lower it.
- Routes electrical, plumbing, carpentry, cleaning, internet, and other issues.
- Joins duplicate complaints using `(room, issue)`.
- Urgent tickets due same day; other tickets due within two days.
- Writes `work_orders.csv`, `results.csv`, `needs_info.csv`, and `summary.txt`.

## Project structure

```text
Hostel_Maintenance_Ticket_Sorter/
├── main.py
├── classifier.py
├── system_prompt.txt
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── data/
│   ├── complaints.csv
│   └── open_tickets.csv
├── reports/
│   └── .gitkeep
├── tests/
│   ├── eval_cases.json
│   ├── red_team_cases.json
│   └── run_tests.py
└── docs/
    ├── project_specification.md
    ├── judgment_framework.md
    ├── cost_and_latency.md
    ├── ai_decision_journal.md
    └── reflection_400_words.md
```

## Requirements

- Python 3.10 or newer
- Internet connection and Gemini API key only if you want LLM mode

## Setup on Windows (IDLE / Command Prompt)

1. Extract the ZIP file.
2. Open the extracted project folder.
3. Click the folder address bar, type `cmd`, and press Enter.
4. Install dependencies:

   ```bash
   py -m pip install -r requirements.txt
   ```

5. (Optional) For LLM mode, create a Gemini API key in [Google AI Studio](https://aistudio.google.com/app/apikey).
6. Copy `.env.example` to `.env` and put your key after `GEMINI_API_KEY=`.
7. Install `python-dotenv` is already included; the program loads `.env` automatically if available.

## Run the project

**Offline mode (no API key needed):**

```bash
py main.py --offline
```

**LLM mode (uses Gemini when a key is configured):**

```bash
py main.py
```

If no key is configured, the program automatically uses its local fallback. Output files are saved in `reports/`.

## Run tests

```bash
py tests/run_tests.py
```

The tests include five evaluation complaints and three red-team scenarios.

## Input format

`complaints.csv` columns:

- `id`: unique complaint ID
- `date`: date in `YYYY-MM-DD`
- `complaint`: natural-language student complaint

`open_tickets.csv` columns:

- `ticket`: existing ticket ID
- `room`: valid room code
- `issue`: issue category
- `opened`: date in `YYYY-MM-DD`

Replace the sample rows with your own data, keeping the column names.

## Output files

- `reports/work_orders.csv`: one row per ticket, urgent first, grouped by team.
- `reports/results.csv`: one result per complaint (new ticket, duplicate, or needs more info).
- `reports/needs_info.csv`: room details requiring warden follow-up.
- `reports/summary.txt`: counts by team and block, plus repeat-complaint rooms.

## GitHub: push your project

Create an empty repository on GitHub (do not add a README there if this folder already has one). In Command Prompt opened inside this project folder, run:

```bash
git init
git status
git add .
git commit -m "Add project specification and sample data"
git add main.py classifier.py system_prompt.txt
git commit -m "Build complaint classification and ticket workflow"
git add tests docs README.md .gitignore
git commit -m "Add evaluation, red-team tests and documentation"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/Hostel-Maintenance-Ticket-Sorter.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username. If Git says the remote already exists, use `git remote set-url origin YOUR-REPOSITORY-URL`.

## Important: protect your API key

- Put your real key only in `.env`.
- `.env` is excluded by `.gitignore`.
- Never paste your key into `main.py`, `classifier.py`, README, screenshots, or GitHub.
- Before pushing, run `git status` and confirm `.env` is not listed.

## Human checkpoint

The warden must read every urgent ticket, assign all work, follow up on missing information, and close tickets. This program never closes a ticket.
