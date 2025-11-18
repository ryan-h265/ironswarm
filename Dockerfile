# Stage 1: Build frontend
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Copy frontend source
COPY src/ironswarm/web/frontend/package*.json ./
COPY src/ironswarm/web/frontend/ ./

# Install dependencies and build
RUN npm ci --quiet && npm run build

# Stage 2: Python runtime
FROM python:3.14-slim-trixie

WORKDIR /usr/src/app

# Copy Python source files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Copy built frontend assets from stage 1
COPY --from=frontend-builder /build/../static/ ./src/ironswarm/web/static/

# Install the package
RUN pip install --no-cache-dir .

CMD ["ironswarm"]