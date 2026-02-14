# Queue Broker System

This document describes the queue broker system for maintaining pending queues and persisting step-wise actions.

## Overview

The queue system now supports multiple broker backends:
- **Internal Queue** (default): In-memory Python list-based queue
- **Redis**: Direct Redis list-based queue
- **Celery**: Celery task queue (uses Redis/RabbitMQ as broker)
- **RabbitMQ**: AMQP-based message queue
- **Kafka**: Apache Kafka distributed streaming platform

The system automatically falls back to the internal queue if the configured broker is not available.

## Configuration

Configure the queue broker in your `.env` file or environment variables:

```bash
# Queue Broker Type: internal, redis, celery, rabbitmq, kafka
QUEUE_BROKER_TYPE=internal

# For Celery - broker URL (defaults to Redis URL if not specified)
QUEUE_BROKER_URL=redis://localhost:6379/0

# Queue name/topic
QUEUE_NAME=command_queue

# RabbitMQ Configuration
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_GROUP_ID=devops_agent

# Queue Persistence
QUEUE_PERSISTENCE_ENABLED=true
QUEUE_PERSISTENCE_PATH=data/queue_state.json
```

## Usage

The `CommandQueue` class automatically uses the configured broker:

```python
from app.services.command_queue import CommandQueue

# Initialize queue (uses settings from config)
queue = CommandQueue()

# Add commands
cmd = queue.add_command("kubectl get pods", round_number=1)

# Mark as executing
queue.mark_executing(cmd)

# Mark as completed
queue.mark_completed(cmd, result)

# Get pending commands
pending = queue.get_pending_commands()

# Get broker status
status = queue.get_broker_status()
print(f"Broker: {status['type']}, Available: {status['available']}")
```

## Persistence

Queue state is automatically persisted to disk (if enabled) to maintain pending queues across restarts:

- Pending commands are saved
- Executed commands are saved
- Current round number is saved
- State is automatically restored on initialization

## Broker Selection Logic

1. The system attempts to use the configured broker type
2. If the broker is not available (connection fails, library missing), it falls back to internal queue
3. All broker operations are logged for debugging

## Supported Brokers

### Internal Queue (Default)
- No external dependencies
- In-memory only
- Fastest for single-process applications
- **Limitation**: Lost on process restart (unless persistence is enabled)

### Redis
- Requires: `redis` library
- Fast and reliable
- Supports persistence via Redis persistence
- Good for single-server deployments

### Celery
- Requires: `celery` library + broker (Redis/RabbitMQ)
- Distributed task execution
- Supports task retries, scheduling
- Best for multi-worker deployments

### RabbitMQ
- Requires: `pika` library
- AMQP protocol
- Reliable message delivery
- Good for enterprise deployments

### Kafka
- Requires: `kafka-python` library
- Distributed streaming
- High throughput
- Best for high-volume, distributed systems

## Step-wise Action Persistence

The queue system maintains step-wise actions by:

1. **Enqueueing**: Each command is added with a unique task ID
2. **Tracking**: Commands are tracked through their lifecycle (pending → executing → completed/failed)
3. **Persistence**: State is saved to disk periodically
4. **Recovery**: On restart, pending commands are restored from persistence

## Example: Using Redis Queue

```python
# In .env file:
QUEUE_BROKER_TYPE=redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
QUEUE_NAME=command_queue

# In code:
from app.services.command_queue import CommandQueue

queue = CommandQueue()
# Automatically uses Redis if available, falls back to internal if not
```

## Monitoring

Check broker status:

```python
status = queue.get_broker_status()
# Returns:
# {
#   'type': 'redis',
#   'available': True,
#   'pending_count': 5
# }
```

## Troubleshooting

1. **Broker not connecting**: Check logs for connection errors. System will fall back to internal queue.
2. **Missing dependencies**: Install required packages:
   - Redis: `pip install redis`
   - Celery: `pip install celery`
   - RabbitMQ: `pip install pika`
   - Kafka: `pip install kafka-python`
3. **Persistence issues**: Check file permissions for `QUEUE_PERSISTENCE_PATH`

