FROM node:22-alpine AS frontend-build
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY sample/ ./sample/
COPY .env.example ./
RUN mkdir -p /app/frontend/dist
COPY --from=frontend-build /web/dist/ /app/frontend/dist/
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8000"]
