FROM python:3.12-slim

WORKDIR /srv/app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY ostrovok_search.py reviews_search.py hotels.json ./

ENV DATABASE_URL=postgresql://easytravel:easytravel@db:5432/easytravel
EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
