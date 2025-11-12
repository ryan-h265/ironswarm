FROM python:3.14-slim-trixie

WORKDIR /usr/src/app

# Copy only files needed for installation
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir .

CMD ["ironswarm"]