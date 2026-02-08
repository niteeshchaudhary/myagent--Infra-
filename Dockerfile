FROM python:3.11-slim

LABEL maintainer="DevOps Team"
LABEL description="DevOps Monitoring Agent for Infrastructure Management"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    wget \\
    gnupg \\
    lsb-release \\
    apt-transport-https \\
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \\
    && chmod +x kubectl \\
    && mv kubectl /usr/local/bin/

# Install AWS CLI
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \\
    && unzip awscliv2.zip \\
    && ./aws/install \\
    && rm -rf aws awscliv2.zip

# Install Google Cloud CLI
RUN curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \\
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \\
    && apt-get update && apt-get install -y google-cloud-cli \\
    && rm -rf /var/lib/apt/lists/*

# Install Azure CLI
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs data/sops data/vector_db

# Create non-root user
RUN useradd --create-home --shell /bin/bash devops \\
    && chown -R devops:devops /app
USER devops

# Expose ports
EXPOSE 8088 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8088/health || exit 1

# Default command
CMD ["python", "main.py"]