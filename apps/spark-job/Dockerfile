FROM spark:3.5.3-scala2.12-java17-python3-ubuntu

USER root

ARG SPARK_HOME=/opt/spark
ARG IVY_DIR=/opt/spark/jars

# Install curl to download JARs at build time
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install psycopg2 for native Postgres upserts in foreachBatch handlers
RUN pip install --no-cache-dir psycopg2-binary==2.9.10

# Spark needs Kafka connector + Postgres driver added to its classpath
RUN curl -L -o ${IVY_DIR}/spark-sql-kafka-0-10_2.12-3.5.3.jar \
    https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.3/spark-sql-kafka-0-10_2.12-3.5.3.jar && \
    curl -L -o ${IVY_DIR}/kafka-clients-3.5.1.jar \
    https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar && \
    curl -L -o ${IVY_DIR}/spark-token-provider-kafka-0-10_2.12-3.5.3.jar \
    https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.3/spark-token-provider-kafka-0-10_2.12-3.5.3.jar && \
    curl -L -o ${IVY_DIR}/commons-pool2-2.11.1.jar \
    https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar && \
    curl -L -o ${IVY_DIR}/postgresql-42.7.3.jar \
    https://jdbc.postgresql.org/download/postgresql-42.7.3.jar

# Copy our streaming application
COPY stock_streaming.py /opt/spark/app/stock_streaming.py

USER spark
WORKDIR /opt/spark/app
