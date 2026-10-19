# BuildScope AI backend: Research Analysis (Module 2) + Stakeholder Intelligence (Module 3)

Read **GUIDE.md** first. Quick start:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add TINYFISH_API_KEY and LLM_API_KEY
docker compose up -d
python -m pytest -q         # 23 tests, fully offline
uvicorn app.main:app --reload   # then open http://localhost:8000/docs
```
