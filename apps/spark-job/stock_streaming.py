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

import os
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
POSTGRES_HOST = "postgres.data.svc.cluster.local"
POSTGRES_PORT = 5432
POSTGRES_DB = "stock_data"
POSTGRES_URL = f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
POSTGRES_USER = os.environ.get("POSTGRES_USER", "stockuser")
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]


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
    """Upsert 1-minute windowed aggregates to 'stocks_aggregates_1m'.

    Uses INSERT ... ON CONFLICT DO UPDATE for idempotent writes. Streaming
    jobs may re-process the same window during failure recovery or restart;
    upsert ensures re-processing produces the same final state without
    primary-key conflicts.
    """
    if batch_df.isEmpty():
        return

    rows = batch_df.collect()

    # psycopg2 imported locally to keep top-level imports for Spark types only
    import psycopg2

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO stocks_aggregates_1m
                        (window_start, window_end, symbol, avg_close, min_low, max_high, trade_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (window_start, symbol)
                    DO UPDATE SET
                        window_end = EXCLUDED.window_end,
                        avg_close = EXCLUDED.avg_close,
                        min_low = EXCLUDED.min_low,
                        max_high = EXCLUDED.max_high,
                        trade_count = EXCLUDED.trade_count
                    """,
                    (
                        row["window_start"],
                        row["window_end"],
                        row["symbol"],
                        row["avg_close"],
                        row["min_low"],
                        row["max_high"],
                        row["trade_count"],
                    ),
                )
        conn.commit()
        print(f"[aggregate] Batch {batch_id}: upserted {len(rows)} window rows")
    finally:
        conn.close()


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