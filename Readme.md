# DevOps Monitoring Agent 🔧

An intelligent infrastructure monitoring and incident management agent that can automatically detect, diagnose, and resolve infrastructure issues across Kubernetes, AWS, GCP, and Azure environments.

## 🌟 Features

### 🔍 Comprehensive Monitoring
- **Polling Monitor**: Continuous infrastructure health checks via CLI commands
- **Webhook Monitor**: Real-time incident alerts from external monitoring systems
- **Multi-Cloud Support**: Kubernetes, AWS, GCP, Azure integration
- **Customizable Check Intervals**: Configurable monitoring frequencies

### 🚨 Intelligent Incident Management
- **Automated Issue Detection**: Identifies infrastructure problems automatically
- **SOP Integration**: Checks Standard Operating Procedures for known solutions
- **Smart Resolution**: Attempts automatic fixes for known issues
- **Audit Trail**: Complete history of all actions and decisions

### 🤖 AI-Powered Resolution
- **Multiple LLM Support**: OpenAI, Groq, and Ollama integration
- **RAG Implementation**: Knowledge base search for SOP documents
- **Internet Search**: Finds solutions for unknown issues
- **Approval Workflow**: Human approval for potentially destructive actions

### 📊 Modern Web Interface
- **Streamlit Dashboard**: Real-time incident monitoring and management
- **Audit Logs**: Complete action history with filtering
- **Configuration Management**: Easy settings management
- **SOP Document Viewer**: Browse and manage knowledge base

### 🔔 Multi-Channel Notifications
- **Messaging Platforms**: Telegram, Slack, Teams, WhatsApp support
- **Email Alerts**: Detailed incident reports and logs
- **Approval Requests**: Interactive approval workflows

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Streamlit UI  │    │   Main Agent     │    │  External APIs  │
│                 │    │                  │    │                 │
│ • Dashboard     │◄──►│ • Polling Mon.   │◄──►│ • Kubernetes    │
│ • Incidents     │    │ • Webhook Mon.   │    │ • AWS           │
│ • Audit Logs    │    │ • Incident Mgmt  │    │ • GCP           │
│ • Configuration │    │ • LLM Integration│    │ • Azure         │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌──────────────────┐
│    Database     │    │      Redis       │
│                 │    │                  │
│ • Incidents     │    │ • Queues         │
│ • Audit Logs    │    │ • Cache          │
│ • SOP Docs      │    │ • Sessions       │
│ • Configuration │    │                  │
└─────────────────┘    └──────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Docker (optional)
- Kubernetes CLI (kubectl)
- Cloud CLIs (aws, gcloud, az) - optional

### 1. Automated Setup

```bash
# Clone the repository
git clone <repository-url>
cd myagent--Infra-

# Run automated setup
python setup.py
```

### 2. Manual Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup configuration
cp .env.template .env
# Edit .env with your configuration

# Initialize database
python -c "from app.database.database import db_service; print('Database initialized')"
```

### 3. Start the Application

```bash
# Start main monitoring agent
python main.py

# In another terminal, start the UI
streamlit run app/ui/main.py
```

### 4. Access the Application

- **Web UI**: http://localhost:8501
- **Webhook API**: http://localhost:8088
- **Health Check**: http://localhost:8088/health

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Using Docker

```bash
# Build image
docker build -t devops-agent .

# Run container
docker run -d \
  --name devops-agent \
  -p 8088:8088 \
  -p 8501:8501 \
  -v $(pwd)/data:/app/data \
  -v ~/.kube:/home/devops/.kube:ro \
  devops-agent
```

## ⚙️ Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
DATABASE_TYPE=sqlite  # or postgresql
DATABASE_URL=postgresql://user:pass@host:port/db

# LLM Provider
LLM_PROVIDER=ollama  # ollama, openai, groq
OPENAI_API_KEY=your_key
GROQ_API_KEY=your_key

# Monitoring
POLLING_INTERVAL=300  # seconds
WEBHOOK_PORT=8088

# Cloud Providers
AWS_PROFILE=your_profile
GCP_PROJECT=your_project
AZURE_SUBSCRIPTION=your_subscription

# Notifications
TELEGRAM_BOT_TOKEN=your_token
SLACK_BOT_TOKEN=your_token
EMAIL_USER=your_email
```

### Webhook Endpoints

The agent supports multiple webhook formats:

- `POST /webhook` - Generic webhook
- `POST /webhook/prometheus` - Prometheus/Alertmanager
- `POST /webhook/grafana` - Grafana alerts
- `POST /webhook/kubernetes` - Kubernetes events

## 📋 How It Works

### 1. Monitoring Modes

**Polling Mode:**
- Runs CLI commands at configured intervals
- Checks pod status, node health, service availability
- Detects infrastructure anomalies automatically

**Webhook Mode:**
- Receives real-time alerts from monitoring systems
- Processes Prometheus, Grafana, and custom alerts
- Converts alerts into actionable incidents

### 2. Incident Resolution Workflow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Detect    │───►│   Analyze   │───►│   Resolve   │
│   Issue     │    │   with SOP  │    │  Automatic/ │
│             │    │             │    │   Manual    │
└─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │
       │                   ▼                   │
       │           ┌─────────────┐             │
       │           │  Query LLM  │             │
       │           │  for Help   │             │
       │           └─────────────┘             │
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────┐
│              Audit & History                    │
└─────────────────────────────────────────────────┘
```

### 3. Approval System

For potentially destructive actions:
1. System identifies high-risk operations
2. Sends approval request via configured channels
3. Waits for human approval before proceeding
4. Logs all approval decisions and outcomes

## 📚 SOP Integration

The system uses Standard Operating Procedures (SOPs) for:

- **Known Issue Resolution**: Automatic fixes for documented problems
- **Guided Troubleshooting**: Step-by-step resolution instructions
- **Knowledge Base**: Searchable repository of solutions
- **Effectiveness Tracking**: Success rates for different procedures

### Example SOP Structure

```markdown
# Kubernetes Pod Troubleshooting

## Overview
Steps to resolve common pod issues

## Common Issues

### Pod Stuck in Pending
**Symptoms:** Pod shows "Pending" status
**Resolution:**
1. Check node resources: `kubectl describe nodes`
2. Verify PVC availability
3. Check node selectors

### CrashLoopBackOff
**Symptoms:** Frequent pod restarts
**Resolution:**
1. Check logs: `kubectl logs pod-name --previous`
2. Verify resource limits
3. Check health probes
```

## 🔧 Development

### Project Structure

```
myagent--Infra-/
├── app/
│   ├── database/          # Database models and services
│   ├── models/           # SQLAlchemy models
│   ├── monitoring/       # Polling and webhook monitors
│   ├── ui/              # Streamlit interface
│   ├── llm/             # LLM integrations
│   ├── approval_system/ # Notification channels
│   └── sop_rag/         # RAG implementation
├── config/              # Configuration management
├── data/                # Data storage
│   ├── sops/           # SOP documents
│   └── vector_db/      # Vector database
├── logs/               # Application logs
└── tests/              # Test suite
```

### Adding New Monitoring Checks

```python
from app.monitoring.polling_monitor import MonitoringCheck, IncidentSeverity

# Define custom check
def check_custom_service(result):
    issues = []
    # Your check logic here
    return issues

# Add to monitor
custom_check = MonitoringCheck(
    name="custom_service_check",
    command="your-command",
    check_function=check_custom_service,
    interval_seconds=300,
    severity=IncidentSeverity.HIGH
)

polling_monitor.add_custom_check(custom_check)
```

### Adding New Webhook Processors

```python
def process_custom_webhook(payload, headers):
    """Process custom webhook format"""
    incidents = []
    # Your processing logic here
    return incidents

# Register processor
webhook_monitor.webhook_processors['custom'] = process_custom_webhook
```

## 📊 Monitoring and Observability

### Metrics and Logging

- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Audit Trail**: Complete history of all system actions
- **Health Checks**: Built-in health endpoints for monitoring
- **Performance Metrics**: Execution times and success rates

### Dashboard Features

- **Real-time Incident Board**: Live status of infrastructure issues
- **Trend Analysis**: Historical incident patterns and frequencies
- **Resolution Metrics**: Success rates and resolution times
- **System Health**: Monitor the monitoring system itself

## 🔒 Security

### Best Practices

- **Principle of Least Privilege**: Limited command whitelist
- **Secure Secrets Management**: Environment variable based configuration
- **Audit Logging**: All actions tracked and logged
- **Webhook Signature Verification**: HMAC signature validation
- **Input Validation**: Sanitized command parameters

### Command Safety

The system only allows pre-approved commands:
- Read-only operations by default
- Explicit whitelist of allowed commands
- Human approval required for destructive operations
- Command output sanitization

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new features
5. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements.txt
pip install pytest black flake8 mypy

# Run tests
pytest

# Format code
black .

# Type checking
mypy app/
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Documentation**: Check the `/docs` directory for detailed guides
- **Issues**: Report bugs and feature requests on GitHub
- **Discussions**: Join community discussions on GitHub Discussions

## 🗺️ Roadmap

- [ ] Machine Learning for anomaly detection
- [ ] Integration with more monitoring systems
- [ ] Mobile app for incident management
- [ ] Advanced reporting and analytics
- [ ] Multi-tenant support
- [ ] API rate limiting and throttling
- [ ] Custom alert rule engine
