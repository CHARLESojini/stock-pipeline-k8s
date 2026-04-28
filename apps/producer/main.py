"""
Stock data producer for Kafka.

Fetches OHLC data from Alpha Vantage via RapidAPI, publishes JSON messages
to Kafka topic 'stock_analysis'. Runs once per invocation (designed for K8s CronJob).

K8s CronJob handles scheduling; this script just does one fetch+publish cycle and exits.
"""

from extract import connect_to_api, extract_json
from producer_setup import kafka_producer, topic
import sys
import time


def main() -> None:
    """
    Fetch stock data once, publish to Kafka, exit cleanly.

    Designed for Kubernetes CronJob deployment — the scheduler runs this every
    5 minutes. Each invocation is independent.
    """
    try:
        # Fetch stock data from the API
        response = connect_to_api()

        # Extract and format the relevant stock data
        data = extract_json(response)

        if not data:
            print("No data returned from API. Exiting.")
            return

        # Set up the Kafka producer
        producer = kafka_producer()

        # Send each stock record to the Kafka topic
        sent_count = 0
        for stock in data:
            result = {
                'symbol': stock['symbol'],
                'open': float(stock['open']),
                'high': float(stock['high']),
                'low': float(stock['low']),
                'close': float(stock['close']),
                'timestamp': stock['date']
            }

            producer.send(topic, result)
            sent_count += 1

            # Throttle to avoid overwhelming the broker
            time.sleep(0.1)

        # Flush and close the producer
        producer.flush()
        producer.close()

        print(f"Successfully sent {sent_count} records to '{topic}' topic. Exiting.")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)  # Non-zero exit so K8s marks the Job as Failed


if __name__ == '__main__':
    main()