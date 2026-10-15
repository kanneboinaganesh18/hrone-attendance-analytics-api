# Candidate kit

Read in this order:

1. `PROBLEM_STATEMENT.docx`: what you are asked to do, how it is evaluated.
2. `openapi.yaml`: the API contract and the business rules (R1 - R10).
3. `DATA_MODEL.md`: what is stored in MongoDB, with nine sample documents.
4. `app/main.py`: the starter. Put **all** your code in this one file. It must start with `uvicorn app.main:app --port 8000`.
5. `REVIEW.md`, `DECISIONS.md`: templates to fill in.

`sample_data/` holds the nine sample documents as MongoDB Extended JSON; `sample_seed.py` loads them. The grader's dataset is
much larger and contains cases they do not show.

## Local setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set MONGO_URI / MONGO_DB (local docker: docker run -p 27017:27017 mongo:7)
python sample_seed.py
uvicorn app.main:app --port 8000 --reload
```
MongoDB **6.0 or newer** is required (the grader uses 7.0). MongoDB Atlas free tier (M0) works.

## Submit
A public Git repository with `app/main.py`, `requirements.txt`, `REVIEW.md`, `DECISIONS.md` and a short `README.md`.
No `.env`, no secrets, no Dockerfile.

# HROne Attendance & Analytics API

A REST API built with Python, FastAPI, and MongoDB to manage employee attendance, punch-in/punch-out records, attendance corrections, and analytics.

## Features
- Employee creation and listing
- Attendance punch-in and punch-out with business-rule validation
- Attendance record retrieval and corrections with audit history
- Monthly employee attendance analytics
- Department summaries and late-arrival leaderboard
- Department trends and MongoDB query-plan inspection

## Setup
1. Install dependencies:
   `pip install -r requirements.txt`
2. Configure `MONGO_URI` and `MONGO_DB` in your local `.env` file.
3. Start the API:
   `uvicorn app.main:app --port 8000`

## API Documentation
After starting the server, visit `/docs` for interactive Swagger documentation.

## Testing
Run:
`python -m pytest tests/ -v`

## Configuration
Keep `.env` and all database credentials private. Do not commit secrets to GitHub.

