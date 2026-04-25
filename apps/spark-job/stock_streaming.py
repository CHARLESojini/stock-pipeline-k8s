"""
Real-time stock market analysis pipeline (v2 on Kubernetes).

Mirrors v1's data model: same 5 NYSE symbols (AAPL, KOS, TROX, TSLA, WTI),
same OHLC schema, same 5-minute ingest cadence. The only differences from v1
are the runtime architecture (K8s + Spark Operator) and the addition of
windowed aggregations.

Topology:
    Kafka topic 'stock_analysis' (kafka.svc.cluster.local)
        -> Spark Structured Streaming
            -> Postgres 'stocks' table (raw OHLC, mirrors v1)
            -> Postgres 'stocks_aggregates_1m' table (1-min windowed avg/min/max)

Database: stock_data (mirrors v1)
"""

from typing import Dict, List
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    from_json, col, window, avg, count,
    max as spark_max, min as spark_min, to_timestamp
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType
)


# Connection constants — in production these would come from K8s Secrets
KAFKA_BOOTSTRAP = "stock-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
KAFKA_TOPIC = "stock_analysis"
POSTGRES_URL = "jdbc:postgresql://postgres.data.svc.cluster.local:5432/stock_data"
POSTGRES_USER = "stockuser"
POSTGRES_PASSWORD = "changeme_in_prod_use_sealed_secrets"


def build_schema() -> StructType:
    """
    Define the JSON schema of incoming Kafka messages.

    Mirrors v1's OHLC schema from Alpha Vantage:
        symbol, open, high, low, close, timestamp
    """
    return StructType([
        StructField("symbol", StringType(), nullable=False),
        StructField("open", DoubleType(), nullable=False),
        StructField("high", DoubleType(), nullable=False),
        StructField("low", DoubleType(), nullable=False),
        StructField("close", DoubleType(), nullable=False),
        StructField("timestamp", StringType(), nullable=False),
    ])


def write_raw_to_postgres(batch_df: DataFrame, batch_id: int) -> None:
    """Persist raw OHLC records to the 'stocks' table (mirrors v1's main table)."""
    if batch_df.isEmpty():
        return

    (batch_df
        .write
        .format("jdbc")
        .option("url", POSTGRES_URL)
        .option("dbtable", "stocks")
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .mode("append")
        .save())

    print(f"[raw] Batch {batch_id}: wrote {batch_df.count()} OHLC rows to 'stocks'")


def write_aggregates_to_postgres(batch_df: DataFrame, batch_id: int) -> None:
    """Persist 1-minute windowed aggregates to 'stocks_aggregates_1m'."""
    if batch_df.isEmpty():
        return

    (batch_df
        .write
        .format("jdbc")
        .option("url", POSTGRES_URL)
        .option("dbtable", "stocks_aggregates_1m")
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .mode("append")
        .save())

    print(f"[aggregate] Batch {batch_id}: wrote {batch_df.count()} window rows")


def main() -> None:
    """Build and run the dual-sink Spark streaming pipeline."""
    spark = (SparkSession.builder
        .appName("StockMarketAnalysisPipeline")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate())

    spark.sparkContext.setLogLevel("WARN")

    schema = build_schema()

    # Read from Kafka — the source
    raw_stream = (spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load())

    # Parse JSON, cast timestamp to proper Spark TimestampType
    parsed_stream = (raw_stream
        .select(from_json(col("value").cast("string"), schema).alias("data"))
        .select("data.*")
        .withColumn("event_time", to_timestamp(col("timestamp"))))

    # Sink 1: raw OHLC to 'stocks' table (mirrors v1)
    raw_query = (parsed_stream
        .select(
            col("symbol"),
            col("open"),
            col("high"),
            col("low"),
            col("close"),
            col("event_time").alias("timestamp"))
        .writeStream
        .foreachBatch(write_raw_to_postgres)
        .outputMode("append")
        .trigger(processingTime="30 seconds")
        .option("checkpointLocation", "/tmp/spark-checkpoints/stocks-raw")
        .start())

    # Sink 2: 1-minute windowed aggregations
    aggregated = (parsed_stream
        .withWatermark("event_time", "2 minutes")
        .groupBy(
            window(col("event_time"), "1 minute"),
            col("symbol"))
        .agg(
            avg("close").alias("avg_close"),
            spark_min("low").alias("min_low"),
            spark_max("high").alias("max_high"),
            count("close").alias("trade_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("symbol"),
            col("avg_close"),
            col("min_low"),
            col("max_high"),
            col("trade_count")))

    aggregate_query = (aggregated
        .writeStream
        .foreachBatch(write_aggregates_to_postgres)
        .outputMode("update")
        .trigger(processingTime="30 seconds")
        .option("checkpointLocation", "/tmp/spark-checkpoints/stocks-aggregates")
        .start())

    # Wait for either query to terminate (fails-fast if one breaks)
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()