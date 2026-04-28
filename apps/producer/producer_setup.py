from kafka import KafkaProducer
import json
import os

topic = "stock_analysis"

def kafka_producer() -> KafkaProducer:
    """
    Creates and returns a KafkaProducer instance.

    Uses the KAFKA_BOOTSTRAP_SERVER environment variable if set,
    otherwise defaults to localhost:9094 for local development.

    Returns:
        KafkaProducer: The Kafka producer instance.
    """
    bootstrap_server = os.getenv('KAFKA_BOOTSTRAP_SERVER', 'localhost:9094')

    producer = KafkaProducer(
        bootstrap_servers=bootstrap_server,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    return producer