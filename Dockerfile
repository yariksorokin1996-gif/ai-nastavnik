FROM node:20-slim AS webapp-builder

WORKDIR /webapp
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY webapp/ .
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Копируем собранный webapp
COPY --from=webapp-builder /webapp/dist /app/webapp/dist

EXPOSE 8080

CMD ["python", "run.py"]
