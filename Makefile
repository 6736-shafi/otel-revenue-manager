.PHONY: setup etl test api ui all clean

setup:
	python3 -m venv venv
	venv/bin/pip install -r requirements.txt
	venv/bin/playwright install chromium
	docker compose up -d

etl:
	DATABASE_URL=postgresql://hackathon:hackathon@localhost:5433/hotel_hackathon \
		venv/bin/python etl/run_etl.py

fingerprint:
	DATABASE_URL=postgresql://hackathon:hackathon@localhost:5433/hotel_hackathon \
		venv/bin/python scripts/compute_load_fingerprint.py \
		--manifest etl/SCRAPE_MANIFEST.json \
		--output etl/LOAD_PROOF.json

test:
	DATABASE_URL=postgresql://hackathon:hackathon@localhost:5433/hotel_hackathon \
		venv/bin/python -m pytest tests/ -v

api:
	DATABASE_URL=postgresql://hackathon:hackathon@localhost:5433/hotel_hackathon \
		venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	DATABASE_URL=postgresql://hackathon:hackathon@localhost:5433/hotel_hackathon \
		venv/bin/streamlit run ui/app.py --server.port 8501

all: setup etl fingerprint test
