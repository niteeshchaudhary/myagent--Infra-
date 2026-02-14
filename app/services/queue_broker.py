"""Queue broker abstraction layer supporting multiple backends"""

import logging
import json
import pickle
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class QueueBrokerType(Enum):
    """Supported queue broker types"""
    INTERNAL = "internal"
    REDIS = "redis"
    CELERY = "celery"
    RABBITMQ = "rabbitmq"
    KAFKA = "kafka"


class QueueBroker(ABC):
    """Abstract base class for queue brokers"""
    
    @abstractmethod
    def enqueue(self, task_id: str, data: Dict[str, Any]) -> bool:
        """Enqueue a task"""
        pass
    
    @abstractmethod
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a task"""
        pass
    
    @abstractmethod
    def get_pending_count(self) -> int:
        """Get count of pending tasks"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if broker is available"""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all tasks from queue"""
        pass


class InternalQueueBroker(QueueBroker):
    """Internal in-memory queue broker (fallback)"""
    
    def __init__(self):
        self._queue: List[Dict[str, Any]] = []
        self._available = True
        logger.info("Initialized InternalQueueBroker")
    
    def enqueue(self, task_id: str, data: Dict[str, Any]) -> bool:
        """Enqueue a task"""
        try:
            task = {
                'task_id': task_id,
                'data': data,
                'enqueued_at': datetime.now().isoformat()
            }
            self._queue.append(task)
            logger.debug(f"Enqueued task {task_id} to internal queue")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id}: {e}")
            return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a task"""
        if self._queue:
            task = self._queue.pop(0)
            logger.debug(f"Dequeued task {task.get('task_id')} from internal queue")
            return task
        return None
    
    def get_pending_count(self) -> int:
        """Get count of pending tasks"""
        return len(self._queue)
    
    def is_available(self) -> bool:
        """Check if broker is available"""
        return self._available
    
    def clear(self) -> bool:
        """Clear all tasks from queue"""
        self._queue.clear()
        logger.info("Cleared internal queue")
        return True


class RedisQueueBroker(QueueBroker):
    """Redis-based queue broker"""
    
    def __init__(self, host: str = "localhost", port: int = 6379, 
                 db: int = 0, password: Optional[str] = None, 
                 queue_name: str = "command_queue"):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.queue_name = queue_name
        self._redis = None
        self._available = False
        self._connect()
    
    def _connect(self):
        """Connect to Redis"""
        try:
            import redis
            self._redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=False  # We'll handle serialization ourselves
            )
            # Test connection
            self._redis.ping()
            self._available = True
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except ImportError:
            logger.warning("Redis library not available")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self._available = False
    
    def enqueue(self, task_id: str, data: Dict[str, Any]) -> bool:
        """Enqueue a task"""
        if not self.is_available():
            return False
        try:
            task = {
                'task_id': task_id,
                'data': data,
                'enqueued_at': datetime.now().isoformat()
            }
            serialized = pickle.dumps(task)
            self._redis.lpush(self.queue_name, serialized)
            logger.debug(f"Enqueued task {task_id} to Redis queue")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id} to Redis: {e}")
            return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a task"""
        if not self.is_available():
            return None
        try:
            if timeout:
                result = self._redis.brpop(self.queue_name, timeout=int(timeout))
                if result:
                    _, serialized = result
                    task = pickle.loads(serialized)
                    logger.debug(f"Dequeued task {task.get('task_id')} from Redis queue")
                    return task
            else:
                result = self._redis.rpop(self.queue_name)
                if result:
                    task = pickle.loads(result)
                    logger.debug(f"Dequeued task {task.get('task_id')} from Redis queue")
                    return task
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue from Redis: {e}")
            return None
    
    def get_pending_count(self) -> int:
        """Get count of pending tasks"""
        if not self.is_available():
            return 0
        try:
            return self._redis.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get pending count from Redis: {e}")
            return 0
    
    def is_available(self) -> bool:
        """Check if broker is available"""
        if not self._available:
            return False
        try:
            self._redis.ping()
            return True
        except:
            self._available = False
            return False
    
    def clear(self) -> bool:
        """Clear all tasks from queue"""
        if not self.is_available():
            return False
        try:
            self._redis.delete(self.queue_name)
            logger.info("Cleared Redis queue")
            return True
        except Exception as e:
            logger.error(f"Failed to clear Redis queue: {e}")
            return False


class CeleryQueueBroker(QueueBroker):
    """Celery-based queue broker"""
    
    def __init__(self, broker_url: Optional[str] = None, queue_name: str = "command_queue"):
        self.broker_url = broker_url or "redis://localhost:6379/0"
        self.queue_name = queue_name
        self._celery_app = None
        self._available = False
        self._connect()
    
    def _connect(self):
        """Initialize Celery app"""
        try:
            from celery import Celery
            self._celery_app = Celery(
                'devops_agent',
                broker=self.broker_url,
                backend=self.broker_url
            )
            # Test connection
            self._celery_app.control.inspect().active()
            self._available = True
            logger.info(f"Initialized Celery with broker {self.broker_url}")
        except ImportError:
            logger.warning("Celery library not available")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to initialize Celery: {e}")
            self._available = False
    
    def enqueue(self, task_id: str, data: Dict[str, Any]) -> bool:
        """Enqueue a task using Celery"""
        if not self.is_available():
            return False
        try:
            # For Celery, we need to define a task function
            # This is a simplified version - in production, you'd define proper Celery tasks
            task_data = {
                'task_id': task_id,
                'data': data,
                'enqueued_at': datetime.now().isoformat()
            }
            # Store in Redis directly for now (Celery uses Redis as broker)
            import redis
            redis_client = redis.from_url(self.broker_url)
            serialized = pickle.dumps(task_data)
            redis_client.lpush(self.queue_name, serialized)
            logger.debug(f"Enqueued task {task_id} via Celery")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id} via Celery: {e}")
            return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a task"""
        if not self.is_available():
            return None
        try:
            import redis
            redis_client = redis.from_url(self.broker_url)
            if timeout:
                result = redis_client.brpop(self.queue_name, timeout=int(timeout))
                if result:
                    _, serialized = result
                    return pickle.loads(serialized)
            else:
                result = redis_client.rpop(self.queue_name)
                if result:
                    return pickle.loads(result)
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue from Celery: {e}")
            return None
    
    def get_pending_count(self) -> int:
        """Get count of pending tasks"""
        if not self.is_available():
            return 0
        try:
            import redis
            redis_client = redis.from_url(self.broker_url)
            return redis_client.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Failed to get pending count from Celery: {e}")
            return 0
    
    def is_available(self) -> bool:
        """Check if broker is available"""
        return self._available
    
    def clear(self) -> bool:
        """Clear all tasks from queue"""
        if not self.is_available():
            return False
        try:
            import redis
            redis_client = redis.from_url(self.broker_url)
            redis_client.delete(self.queue_name)
            logger.info("Cleared Celery queue")
            return True
        except Exception as e:
            logger.error(f"Failed to clear Celery queue: {e}")
            return False


class RabbitMQQueueBroker(QueueBroker):
    """RabbitMQ-based queue broker"""
    
    def __init__(self, host: str = "localhost", port: int = 5672,
                 username: str = "guest", password: str = "guest",
                 queue_name: str = "command_queue"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.queue_name = queue_name
        self._connection = None
        self._channel = None
        self._available = False
        self._connect()
    
    def _connect(self):
        """Connect to RabbitMQ"""
        try:
            import pika
            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials
            )
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self.queue_name, durable=True)
            self._available = True
            logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")
        except ImportError:
            logger.warning("pika library not available for RabbitMQ")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to connect to RabbitMQ: {e}")
            self._available = False
    
    def enqueue(self, task_id: str, data: Dict[str, Any]) -> bool:
        """Enqueue a task"""
        if not self.is_available():
            return False
        try:
            task = {
                'task_id': task_id,
                'data': data,
                'enqueued_at': datetime.now().isoformat()
            }
            message = pickle.dumps(task)
            self._channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=message,
                properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
            )
            logger.debug(f"Enqueued task {task_id} to RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id} to RabbitMQ: {e}")
            self._reconnect()
            return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a task"""
        if not self.is_available():
            return None
        try:
            method_frame, header_frame, body = self._channel.basic_get(
                queue=self.queue_name,
                auto_ack=False
            )
            if method_frame:
                task = pickle.loads(body)
                self._channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                logger.debug(f"Dequeued task {task.get('task_id')} from RabbitMQ")
                return task
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue from RabbitMQ: {e}")
            self._reconnect()
            return None
    
    def get_pending_count(self) -> int:
        """Get count of pending tasks"""
        if not self.is_available():
            return 0
        try:
            queue = self._channel.queue_declare(queue=self.queue_name, durable=True, passive=True)
            return queue.method.message_count
        except Exception as e:
            logger.error(f"Failed to get pending count from RabbitMQ: {e}")
            return 0
    
    def is_available(self) -> bool:
        """Check if broker is available"""
        if not self._available or not self._connection or self._connection.is_closed:
            return False
        return True
    
    def _reconnect(self):
        """Reconnect to RabbitMQ"""
        try:
            self._connect()
        except Exception as e:
            logger.error(f"Failed to reconnect to RabbitMQ: {e}")
    
    def clear(self) -> bool:
        """Clear all tasks from queue"""
        if not self.is_available():
            return False
        try:
            self._channel.queue_purge(queue=self.queue_name)
            logger.info("Cleared RabbitMQ queue")
            return True
        except Exception as e:
            logger.error(f"Failed to clear RabbitMQ queue: {e}")
            return False


class KafkaQueueBroker(QueueBroker):
    """Kafka-based queue broker"""
    
    def __init__(self, bootstrap_servers: str = "localhost:9092",
                 topic: str = "command_queue", group_id: str = "devops_agent"):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self._producer = None
        self._consumer = None
        self._available = False
        self._connect()
    
    def _connect(self):
        """Connect to Kafka"""
        try:
            from kafka import KafkaProducer, KafkaConsumer
            from kafka.errors import KafkaError
            
            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers.split(','),
                value_serializer=lambda v: pickle.dumps(v)
            )
            
            self._consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers.split(','),
                group_id=self.group_id,
                value_deserializer=lambda m: pickle.loads(m),
                auto_offset_reset='earliest',
                enable_auto_commit=True
            )
            
            self._available = True
            logger.info(f"Connected to Kafka at {self.bootstrap_servers}")
        except ImportError:
            logger.warning("kafka-python library not available")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to connect to Kafka: {e}")
            self._available = False
    
    def enqueue(self, task_id: str, data: Dict[str, Any]) -> bool:
        """Enqueue a task"""
        if not self.is_available():
            return False
        try:
            task = {
                'task_id': task_id,
                'data': data,
                'enqueued_at': datetime.now().isoformat()
            }
            future = self._producer.send(self.topic, task)
            future.get(timeout=10)  # Wait for send to complete
            logger.debug(f"Enqueued task {task_id} to Kafka")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id} to Kafka: {e}")
            return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Dequeue a task"""
        if not self.is_available():
            return None
        try:
            # Kafka consumer polls for messages
            messages = self._consumer.poll(timeout_ms=int(timeout * 1000) if timeout else 1000)
            for topic_partition, records in messages.items():
                for record in records:
                    task = record.value
                    logger.debug(f"Dequeued task {task.get('task_id')} from Kafka")
                    return task
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue from Kafka: {e}")
            return None
    
    def get_pending_count(self) -> int:
        """Get count of pending tasks"""
        # Kafka doesn't provide a direct way to get queue length
        # This is a limitation - we'd need to track it separately
        logger.warning("Kafka doesn't support direct queue length queries")
        return 0
    
    def is_available(self) -> bool:
        """Check if broker is available"""
        return self._available
    
    def clear(self) -> bool:
        """Clear all tasks from queue"""
        # Kafka doesn't support clearing topics easily
        logger.warning("Kafka doesn't support clearing topics - consider using a new topic")
        return False


def create_queue_broker(broker_type: str, **kwargs) -> QueueBroker:
    """Factory function to create a queue broker instance"""
    try:
        broker_enum = QueueBrokerType(broker_type.lower())
    except ValueError:
        logger.warning(f"Unknown broker type: {broker_type}, falling back to internal")
        broker_enum = QueueBrokerType.INTERNAL
    
    if broker_enum == QueueBrokerType.REDIS:
        broker = RedisQueueBroker(**kwargs)
        if broker.is_available():
            return broker
        logger.warning("Redis broker not available, falling back to internal")
    
    elif broker_enum == QueueBrokerType.CELERY:
        broker = CeleryQueueBroker(**kwargs)
        if broker.is_available():
            return broker
        logger.warning("Celery broker not available, falling back to internal")
    
    elif broker_enum == QueueBrokerType.RABBITMQ:
        broker = RabbitMQQueueBroker(**kwargs)
        if broker.is_available():
            return broker
        logger.warning("RabbitMQ broker not available, falling back to internal")
    
    elif broker_enum == QueueBrokerType.KAFKA:
        broker = KafkaQueueBroker(**kwargs)
        if broker.is_available():
            return broker
        logger.warning("Kafka broker not available, falling back to internal")
    
    # Fallback to internal queue
    return InternalQueueBroker()

