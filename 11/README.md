# Assignment 11

## Introduction
This week, we are adding Hadoop to our cluster so that we can write files to it.  Instead of using PySpark, we will be using spark-submit to land the events into HDFS.

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
The difference for this week is the addition of the Cloudera image for HDFS.

## Update the images
```
docker pull confluentinc/cp-zookeeper:latest
docker pull confluentinc/cp-kafka:latest
docker pull midsw205/cdh-minimal:latest
docker pull midsw205/spark-python:0.0.5
docker pull midsw205/base:latest
```

## Start the cluster
```
docker-compose up -d
```

## Check the HDFS
```
docker-compose exec cloudera hadoop fs -ls /tmp/
```
As expected there are already YARN and Hive directories.
```
Found 2 items
drwxrwxrwt   - mapred mapred              0 2018-02-06 18:27 /tmp/hadoop-yarn
drwx-wx-wx   - root   supergroup          0 2018-07-17 04:42 /tmp/hive
```

## Check the HDFS and Kafka logs
In separate terminals, I check the logs.
```
docker-compose logs -f cloudera
docker-compose logs -f kafka
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
    return "\nThis is the default response!\n"


@app.route("/purchase_a_sword")
def purchase_a_sword():
    purchase_sword_event = {'event_type': 'purchase_sword'}
    log_to_kafka('events', purchase_sword_event)
    return "\nSword Purchased!\n"
```
We are logging the event type and HTTP headers to Kafka.

## Start the Flask app
```
docker-compose exec mids env FLASK_APP=/w205/assignment-11-hougrammer/game_api.py flask run
```
The terminal is now running `game_api` on localhost port 5000
```
 * Serving Flask app "game_api"
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

## Make calls to the API
Using another terminal, I run the following commands.
```
docker-compose exec mids curl http://localhost:5000/
docker-compose exec mids curl http://localhost:5000/purchase_a_sword
```
I receive the following responses:
```
This is the default response!
Sword Purchased!
```
Inside the Flask app, the HTTP GETs are logged:
```
127.0.0.1 - - [17/Jul/2018 04:46:00] "GET / HTTP/1.1" 200 -
127.0.0.1 - - [17/Jul/2018 04:46:05] "GET /purchase_a_sword HTTP/1.1" 200 -
```

## Check the Kafka topic
```
docker-compose exec mids bash -c "kafkacat -C -b kafka:29092 -t events -o beginning -e"
```
```
{"Host": "localhost:5000", "event_type": "default", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"Host": "localhost:5000", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
% Reached end of topic events [0] at offset 2: exiting
```
As expected, we have two events in the topic.

## Create the `extract_events` job
I exec into a mids bash and create `extract_events.py`
```python
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession


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

    events = raw_events.select(raw_events.value.cast('string'))
    extracted_events = events.rdd.map(lambda x: json.loads(x.value)).toDF()

    extracted_events \
        .write \
        .parquet("/tmp/extracted_events")


if __name__ == "__main__":
    main()
```
We create a Spark session and use it extract the events from Kafka.  We cast the raw event binaries into strings and extract the JSON structure.  Then we write the extracted events as Parquet files to HDFS.

## Submit the `extract_events` job
```
docker-compose exec spark spark-submit /w205/assignment-11-hougrammer/extract_events.py
```

## Make sure the files are written to HDFS
```
docker-compose exec cloudera hadoop fs -ls /tmp/
```
There is now an `extracted_events` directory.
```
Found 3 items
drwxr-xr-x   - root   supergroup          0 2018-07-17 04:51 /tmp/extracted_events
drwxrwxrwt   - mapred mapred              0 2018-02-06 18:27 /tmp/hadoop-yarn
drwx-wx-wx   - root   supergroup          0 2018-07-17 04:42 /tmp/hive
```
Inside it we expect to find the Parquet file.
```
docker-compose exec cloudera hadoop fs -ls /tmp/extracted_events/
```
```
Found 2 items
-rw-r--r--   1 root supergroup          0 2018-07-17 04:51 /tmp/extracted_events/_SUCCESS
-rw-r--r--   1 root supergroup       1163 2018-07-17 04:51 /tmp/extracted_events/part-00000-d990e4dc-d8bf-422a-8738-64d0f982dc98-c000.snappy.parquet
```

## Create the `transform_events` job
I exec into a mids bash and create `transform_events.py`
```python
#!/usr/bin/env python
"""Extract events from kafka, transform, and write to hdfs
"""
import json
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import udf


@udf('string')
def munge_event(event_as_json):
    event = json.loads(event_as_json)
    event['Host'] = "moe" # silly change to show it works
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
    munged_events.show()

    extracted_events = munged_events \
        .rdd \
        .map(lambda r: Row(timestamp=r.timestamp, **json.loads(r.munged))) \
        .toDF()
    extracted_events.show()

    extracted_events \
        .write \
        .mode("overwrite") \
        .parquet("/tmp/extracted_events")


if __name__ == "__main__":
    main()
```
We overwrite the 'Host' and 'Cache-Control' parameters in the events just to show that we can transform the data.  Then we overwrite the existing Parquet files.

## Submit the `transform_events` job
```
docker-compose exec spark spark-submit /w205/assignment-11-hougrammer/transform_events.py
```
In this job we did a `show` on the data as well.

|Accept|Cache-Control|Host| User-Agent|    event_type|           timestamp|
|------|-------------|----|-----------|--------------|--------------------|
|   */*|     no-cache| moe|curl/7.47.0|       default|2018-07-17 04:46:...|
|   */*|     no-cache| moe|curl/7.47.0|purchase_sword|2018-07-17 04:46:...|

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
    event['Host'] = "moe" # silly change to show it works
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

## Submit the `separate_events` job
```
docker-compose exec spark spark-submit /w205/assignment-11-hougrammer/separate_events.py
```
We now have two separate RDDs.

|Accept|Cache-Control|Host| User-Agent|    event_type|           timestamp|
|------|-------------|----|-----------|--------------|--------------------|
|   */*|     no-cache| moe|curl/7.47.0|purchase_sword|2018-07-17 04:46:...|


|Accept|Cache-Control|Host| User-Agent|event_type|           timestamp|
|------|-------------|----|-----------|----------|--------------------|
|   */*|     no-cache| moe|curl/7.47.0|   default|2018-07-17 04:46:...|

## Check HDFS for the new directories
```
docker-compose exec cloudera hadoop fs -ls /tmp
```
```
Found 5 items
drwxr-xr-x   - root   supergroup          0 2018-07-17 05:01 /tmp/default_hits
drwxr-xr-x   - root   supergroup          0 2018-07-17 04:57 /tmp/extracted_events
drwxrwxrwt   - mapred mapred              0 2018-02-06 18:27 /tmp/hadoop-yarn
drwx-wx-wx   - root   supergroup          0 2018-07-17 04:42 /tmp/hive
drwxr-xr-x   - root   supergroup          0 2018-07-17 05:01 /tmp/sword_purchases
```

## Enhance the game API
I update `game_api.py`
```
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
    log_to_kafka('events', {'event_type': 'default'})
    return "\nThis is the default response\n"

@app.route("/purchase_item")
def purchase_item():
    item = request.args.get('item')
    if item is None:
        log_to_kafka('events', {
            'event_type': 'purchase_item',
            'item': 'missing'
        })
        return '\nMissing item\n'
    if item not in ['sword', 'knife']:
        log_to_kafka('events', {
            'event_type': 'purchase_item',
            'item': 'invalid'
        })
        return '\nInvalid item\n'
        
    log_to_kafka('events', {
        'event_type': 'purchase_item',
        'item': item
    })
    return "\nBought %s\n" % item
        
@app.route("/join_guild")
def join_guild():
    guild_id = request.args.get('guild_id')
    if guild_id is None:
        log_to_kafka('events', {
            'event_type': 'join_guild',
            'guild_id': 'missing'
        })
        return "\nMissing guild ID\n"
        
    try:
        log_to_kafka('events', {
            'event_type': 'join_guild',
            'guild_id': int(guild_id)
        })
        return "\nJoined guild %d\n" % int(guild_id)
    except:
        log_to_kafka('events', {
            'event_type': 'join_guild',
            'guild_id': 'invalid'
        })
        return "\nInvalid guild ID\n"
```
We now have a purchase_item method which only accepts swords and knives. We also have a join_guild method which accept integer guild IDs.

## Make calls to the new API
I create `api_tests.py`
```python
import requests

assert requests.get('http://localhost:5000/').text == '\nThis is the default response\n'
assert requests.get('http://localhost:5000/purchase_item').text == '\nMissing item\n'
assert requests.get('http://localhost:5000/purchase_item?item=sword').text == '\nBought sword\n'
assert requests.get('http://localhost:5000/purchase_item?item=knife').text == '\nBought knife\n'
assert requests.get('http://localhost:5000/purchase_item?item=shield').text == '\nInvalid item\n'
assert requests.get('http://localhost:5000/join_guild').text == '\nMissing guild ID\n'
assert requests.get('http://localhost:5000/join_guild?guild_id=1').text == '\nJoined guild 1\n'
assert requests.get('http://localhost:5000/join_guild?guild_id=a').text == '\nInvalid guild ID\n'

print('Tests passed')
```
I run the API tests
```
docker-compose exec mids python3 assignment-11-hougrammer/api_tests.py
```
```
Tests passed
```
As expected, the events show up in the Flask server terminal:
```
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET / HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /purchase_item HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /purchase_item?item=sword HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /purchase_item?item=knife HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /purchase_item?item=shield HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /join_guild HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /join_guild?guild_id=1 HTTP/1.1" 200 -
127.0.0.1 - - [14/Jul/2018 04:09:26] "GET /join_guild?guild_id=a HTTP/1.1" 200 -
```
And also in the Kafka topic
```
{"Host": "localhost:5000", "event_type": "default", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"item": "sword", "Host": "localhost:5000", "event_type": "purchase_item", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"item": "missing", "Host": "localhost:5000", "event_type": "purchase_item", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"Host": "localhost:5000", "guild_id": "missing", "event_type": "join_guild", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"Host": "localhost:5000", "guild_id": 1, "event_type": "join_guild", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"Host": "localhost:5000", "guild_id": "invalid", "event_type": "join_guild", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"Accept-Encoding": "gzip, deflate", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "Connection": "keep-alive", "event_type": "default"}
{"Accept-Encoding": "gzip, deflate", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "Connection": "keep-alive", "event_type": "default"}
{"Accept-Encoding": "gzip, deflate", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "Connection": "keep-alive", "event_type": "default"}
{"event_type": "purchase_item", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "item": "missing", "Connection": "keep-alive", "Accept-Encoding": "gzip, deflate"}
{"event_type": "purchase_item", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "item": "sword", "Connection": "keep-alive", "Accept-Encoding": "gzip, deflate"}
{"event_type": "purchase_item", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "item": "knife", "Connection": "keep-alive", "Accept-Encoding": "gzip, deflate"}
{"event_type": "purchase_item", "Host": "localhost:5000", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "item": "invalid", "Connection": "keep-alive", "Accept-Encoding": "gzip, deflate"}
{"event_type": "join_guild", "Connection": "keep-alive", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "Host": "localhost:5000", "guild_id": "missing", "Accept-Encoding": "gzip, deflate"}
{"event_type": "join_guild", "Connection": "keep-alive", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "Host": "localhost:5000", "guild_id": 1, "Accept-Encoding": "gzip, deflate"}
{"event_type": "join_guild", "Connection": "keep-alive", "Accept": "*/*", "User-Agent": "python-requests/2.18.4", "Host": "localhost:5000", "guild_id": "invalid", "Accept-Encoding": "gzip, deflate"}
```

## Update `separate_events`
```
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import udf


@udf('string')
def munge_event(event_as_json):
    event = json.loads(event_as_json)

    if event['event_type'] == 'default':
        event['parameter'] = None
    elif event['event_type'] == 'purchase_item':
        event['parameter'] = event['item']
        del event['item']
    elif event['event_type'] == 'join_guild':
        event['parameter'] = event['guild_id']
        del event['guild_id']

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

    default_hits = extracted_events \
        .filter(extracted_events.event_type == 'default')
    default_hits.show()
    default_hits \
        .write \
        .mode("overwrite") \
        .parquet("/tmp/default_hits")

    item_purchases = extracted_events \
        .filter(extracted_events.event_type == 'purchase_item')
    item_purchases.show()
    item_purchases \
        .write \
        .mode("overwrite") \
        .parquet("/tmp/item_purchases")

    guild_joins = extracted_events \
        .filter(extracted_events.event_type == 'join_guild')
    guild_joins.show()
    guild_joins \
        .write \
        .mode("overwrite") \
        .parquet("/tmp/guild_joins")
    


if __name__ == "__main__":
    main()
```
We now update the `munge_event` to collapse all the HTTP parameters to one column.  We also write to three different HDFS directories.

## Submit the `separate_events` job
```
docker-compose exec spark spark-submit /w205/assignment-11-hougrammer/separate_events.py
```
We showed three different RDDs

|Accept|Accept-Encoding|Connection|          Host|          User-Agent|event_type|parameter|           timestamp|
|------|---------------|----------|--------------|--------------------|----------|---------|--------------------|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|   default|     null|2018-07-19 02:52:...|

|Accept|Accept-Encoding|Connection|          Host|          User-Agent|   event_type|parameter|           timestamp|
|------|---------------|----------|--------------|--------------------|----------|---------|--------------------|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|purchase_item|  missing|2018-07-19 02:52:...|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|purchase_item|    sword|2018-07-19 02:52:...|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|purchase_item|    knife|2018-07-19 02:52:...|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|purchase_item|  invalid|2018-07-19 02:52:...|


|Accept|Accept-Encoding|Connection|          Host|          User-Agent|event_type|parameter|           timestamp|
|------|---------------|----------|--------------|--------------------|----------|---------|--------------------|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|join_guild|  missing|2018-07-19 02:52:...|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|join_guild|        1|2018-07-19 02:52:...|
|   */*|  gzip, deflate|keep-alive|localhost:5000|python-requests/2...|join_guild|  invalid|2018-07-19 02:52:...|

## Verify the three different directories in HDFS
```
docker-compose exec cloudera hadoop fs -ls /tmp
```
```
Found 5 items
drwxr-xr-x   - root   supergroup          0 2018-07-19 02:54 /tmp/default_hits
drwxr-xr-x   - root   supergroup          0 2018-07-19 02:54 /tmp/guild_joins
drwxrwxrwt   - mapred mapred              0 2018-02-06 18:27 /tmp/hadoop-yarn
drwx-wx-wx   - root   supergroup          0 2018-07-19 02:05 /tmp/hive
drwxr-xr-x   - root   supergroup          0 2018-07-19 02:54 /tmp/item_purchases
```

## Tear down the cluster
```
docker-compose down
```

## Summary
This week we added HDFS to the cluster and used it to store results from spark-submit jobs that extracted the events from Kafka.

## Enhancements
* Changed `purchase_a_sword` to `purchase_item` which accepts an item parameter
* Implemented `join_guild` which accepts a guild ID
* Wrote custom event munger to parse events different event types
