FROM python:3.12-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    chromium \
    chromium-driver \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Clone OpenManus repository
RUN git clone https://github.com/FoundationAgents/OpenManus.git .

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies
RUN pip install -r requirements.txt

# Install Playwright browsers
RUN playwright install

# Copy configuration template
RUN if [ -f config/config.example.toml ]; then cp config/config.example.toml config/config.toml; fi

# Expose port for API server
EXPOSE 8000

# Default command
CMD ["python", "main.py"]
