# Assignment 12

## Introduction
This week, we will be using Apache Bench to stress test our server.  Also we will running more Spark jobs, including ones in a Jupyter notebook.

## Setup the assignment repo
```
docker run -it --rm -v ~/w205:/w205 midsw205/base bash
```

First I start a MIDS container to set up my repo.  Inside, I create a `docker-compose.yml` file:

```
---
version: '2'
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 32181
      ZOOKEEPER_TICK_TIME: 2000
    expose:
      - "2181"
      - "2888"
      - "32181"
      - "3888"
    extra_hosts:
      - "moby:127.0.0.1"

  kafka:
    image: confluentinc/cp-kafka:latest
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:32181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    expose:
      - "9092"
      - "29092"
    extra_hosts:
      - "moby:127.0.0.1"

  cloudera:
    image: midsw205/cdh-minimal:latest
    expose:
      - "8020" # nn
      - "50070" # nn http
      - "8888" # hue
    #ports:
    #- "8888:8888"
    extra_hosts:
      - "moby:127.0.0.1"

  spark:
    image: midsw205/spark-python:0.0.5
    stdin_open: true
    tty: true
    expose:
      - "8888"
    ports:
      - "8888:8888"
    volumes:
      - "~/w205:/w205"
    command: bash
    depends_on:
      - cloudera
    environment:
      HADOOP_NAMENODE: cloudera
    extra_hosts:
      - "moby:127.0.0.1"

  mids:
    image: midsw205/base:latest
    stdin_open: true
    tty: true
    expose:
      - "5000"
    ports:
      - "5000:5000"
    volumes:
      - "~/w205:/w205"
    extra_hosts:
      - "moby:127.0.0.1"
      
```

## Update the images
```
docker pull confluentinc/cp-zookeeper:latest
docker pull confluentinc/cp-kafka:latest
docker pull midsw205/cdh-minimal:latest
docker pull midsw205/spark-python:0.0.5
docker pull midsw205/base:0.1.9
```

## Start the cluster
```
docker-compose up -d
```

## Create a Kafka topic to store the events
```
docker-compose exec kafka kafka-topics --create --topic events --partitions 1 --replication-factor 1 --if-not-exists --zookeeper zookeeper:32181
```

## Create the Flask app
I exec into a mids bash and create `game_api.py`
```python
#!/usr/bin/env python
import json
from kafka import KafkaProducer
from flask import Flask, request

app = Flask(__name__)
producer = KafkaProducer(bootstrap_servers='kafka:29092')


def log_to_kafka(topic, event):
    event.update(request.headers)
    producer.send(topic, json.dumps(event).encode())


@app.route("/")
def default_response():
    default_event = {'event_type': 'default'}
    log_to_kafka('events', default_event)
    return "This is the default response!\n"


@app.route("/purchase_a_sword")
def purchase_a_sword():
    purchase_sword_event = {'event_type': 'purchase_sword'}
    log_to_kafka('events', purchase_sword_event)
    return "Sword Purchased!\n"
```
We are logging the event type and HTTP headers to Kafka.

## Start the Flask app
```
docker-compose exec mids env FLASK_APP=/w205/assignment-12-hougrammer/game_api.py flask run
```
The terminal is now running `game_api` on localhost port 5000
```
 * Serving Flask app "game_api"
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

## Set up Kafkacat to continuously print events
In another terminal, I run
```
docker-compose exec mids kafkacat -C -b kafka:29092 -t events -o beginning
```

## Use Apache Bench to repeatedly call the API
In another terminal, I run the following commands.
```
docker-compose exec mids ab -n 10 -H "Host: user1.comcast.com" http://localhost:5000/
docker-compose exec mids ab -n 10 -H "Host: user1.comcast.com" http://localhost:5000/purchase_a_sword
docker-compose exec mids ab -n 10 -H "Host: user2.att.com" http://localhost:5000/
docker-compose exec mids ab -n 10 -H "Host: user2.att.com" http://localhost:5000/purchase_a_sword
```
Here is the output after the first command:
```
This is ApacheBench, Version 2.3 <$Revision: 1706008 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking localhost (be patient).....done


Server Software:        Werkzeug/0.14.1
Server Hostname:        localhost
Server Port:            5000

Document Path:          /
Document Length:        30 bytes

Concurrency Level:      1
Time taken for tests:   0.030 seconds
Complete requests:      10
Failed requests:        0
Total transferred:      1850 bytes
HTML transferred:       300 bytes
Requests per second:    328.00 [#/sec] (mean)
Time per request:       3.049 [ms] (mean)
Time per request:       3.049 [ms] (mean, across all concurrent requests)
Transfer rate:          59.26 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    1   2.4      0       8
Processing:     1    2   1.2      2       6
Waiting:        1    2   1.3      2       5
Total:          1    3   2.8      2      10

Percentage of the requests served within a certain time (ms)
  50%      2
  66%      2
  75%      3
  80%      6
  90%     10
  95%     10
  98%     10
  99%     10
 100%     10 (longest request)
```
In addition, the corresponding events are logged by both the Flask and Kafkacat terminals.

## Create the `separate_events` job
I exec into a mids bash and create `separate_events.py`
```python
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import udf


@udf('string')
def munge_event(event_as_json):
    event = json.loads(event_as_json)
    event['Host'] = "moe"
    event['Cache-Control'] = "no-cache"
    return json.dumps(event)


def main():
    """main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .getOrCreate()

    raw_events = spark \
        .read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()

    munged_events = raw_events \
        .select(raw_events.value.cast('string').alias('raw'),
                raw_events.timestamp.cast('string')) \
        .withColumn('munged', munge_event('raw'))

    extracted_events = munged_events \
        .rdd \
        .map(lambda r: Row(timestamp=r.timestamp, **json.loads(r.munged))) \
        .toDF()

    sword_purchases = extracted_events \
        .filter(extracted_events.event_type == 'purchase_sword')
    sword_purchases.show()
    sword_purchases \
        .write \
        .mode("overwrite") \
        .parquet("/tmp/sword_purchases")

    default_hits = extracted_events \
        .filter(extracted_events.event_type == 'default')
    default_hits.show()
    default_hits \
        .write \
        .mode("overwrite") \
        .parquet("/tmp/default_hits")


if __name__ == "__main__":
    main()
```
The job just separates the two different types of events.  Currently, it can only handle one type of schema.

## Submit the `separate_events` job
```
docker-compose exec spark spark-submit /w205/assignment-12-hougrammer/separate_events.py
```
Here are the results of the two `show()`s

|Accept|Cache-Control|Host| User-Agent|    event_type|           timestamp|
|------|-------------|----|-----------|--------------|--------------------|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|

|Accept|Cache-Control|Host| User-Agent|event_type|           timestamp|
|------|-------------|----|-----------|----------|--------------------|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 22:58:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|
|   */*|     no-cache| moe|ApacheBench/2.3|   default|2018-07-21 23:00:...|


## Check HDFS for the new directories
```
docker-compose exec cloudera hadoop fs -ls /tmp
```
```
Found 4 items
drwxr-xr-x   - root   supergroup          0 2018-07-21 23:10 /tmp/default_hits
drwxrwxrwt   - mapred mapred              0 2018-02-06 18:27 /tmp/hadoop-yarn
drwx-wx-wx   - root   supergroup          0 2018-07-21 22:53 /tmp/hive
drwxr-xr-x   - root   supergroup          0 2018-07-21 23:10 /tmp/sword_purchases
```

## Create the `just_filtering` job
I exec into a mids bash and create `just_filtering.py`
```python
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import udf


@udf('boolean')
def is_purchase(event_as_json):
    event = json.loads(event_as_json)
    if event['event_type'] == 'purchase_sword':
        return True
    return False


def main():
    """main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .getOrCreate()

    raw_events = spark \
        .read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()

    purchase_events = raw_events \
        .select(raw_events.value.cast('string').alias('raw'),
                raw_events.timestamp.cast('string')) \
        .filter(is_purchase('raw'))

    extracted_purchase_events = purchase_events \
        .rdd \
        .map(lambda r: Row(timestamp=r.timestamp, **json.loads(r.raw))) \
        .toDF()
    extracted_purchase_events.printSchema()
    extracted_purchase_events.show()


if __name__ == "__main__":
    main()
```
This job just extracts the purchase events with a UDF.  It leaves the host and cache control alone.

## Submit the `just_filtering` job
```
docker-compose exec spark spark-submit /w205/assignment-12-hougrammer/just_filtering.py
```

|Accept|Cache-Control|Host| User-Agent|    event_type|           timestamp|
|------|-------------|----|-----------|--------------|--------------------|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|user1.comcast.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|
|   */*|    user2.att.com|ApacheBench/2.3|purchase_sword|2018-07-21 23:00:...|

## Add another event to the API
I append the following code to `game_api.py`
```
@app.route("/purchase_a_knife")
def purchase_a_knife():
    purchase_knife_event = {'event_type': 'purchase_knife',
                            'description': 'very sharp knife'}
    log_to_kafka('events', purchase_knife_event)
    return "Knife Purchased!\n"
```
Note that this event has a `description` parameter, which means its schema is different from the other two events.

## Create the `filtered_writes` job
I exec into a mids bash and create `filtered_writes.py`
```python
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import udf


@udf('boolean')
def is_purchase(event_as_json):
    event = json.loads(event_as_json)
    if event['event_type'] == 'purchase_sword':
        return True
    return False


def main():
    """main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .getOrCreate()

    raw_events = spark \
        .read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()

    purchase_events = raw_events \
        .select(raw_events.value.cast('string').alias('raw'),
                raw_events.timestamp.cast('string')) \
        .filter(is_purchase('raw'))

    extracted_purchase_events = purchase_events \
        .rdd \
        .map(lambda r: Row(timestamp=r.timestamp, **json.loads(r.raw))) \
        .toDF()
    extracted_purchase_events.printSchema()
    extracted_purchase_events.show()

    extracted_purchase_events \
        .write \
        .mode('overwrite') \
        .parquet('/tmp/purchases')


if __name__ == "__main__":
    main()
```
This job just extracts the purchase events with a UDF.  It leaves the host and cache control alone.

## Submit the `filtered_writes` job
```
docker-compose exec spark spark-submit /w205/assignment-12-hougrammer/filtered_writes.py
```

## Check HDFS for the new directory
```
docker-compose exec cloudera hadoop fs -ls /tmp
```
```
Found 5 items
drwxr-xr-x   - root   supergroup          0 2018-07-21 23:10 /tmp/default_hits
drwxrwxrwt   - mapred mapred              0 2018-02-06 18:27 /tmp/hadoop-yarn
drwx-wx-wx   - root   supergroup          0 2018-07-21 22:53 /tmp/hive
drwxr-xr-x   - root   supergroup          0 2018-07-21 23:32 /tmp/purchases
drwxr-xr-x   - root   supergroup          0 2018-07-21 23:10 /tmp/sword_purchases
```

## Start a Jupyter notebook
```
docker-compose exec spark env PYSPARK_DRIVER_PYTHON=jupyter PYSPARK_DRIVER_PYTHON_OPTS='notebook --no-browser --port 8888 --ip 0.0.0.0 --allow-root' pyspark
```
The notebook is annotated elsewhere in this repo.

## Tear down the cluster
```
docker-compose down
```

## Summary
This week we used Apache bench to repeatedly call the web API and used PySpark in a Jupyter notebook.
