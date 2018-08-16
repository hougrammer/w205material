# Assignment 10

## Introduction
This week, we are modifying the game APIs from last week to log events in JSON instead of plaintext.  In addition, we are adding Spark to extract the events from Kafka.

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

  spark:
    image: midsw205/spark-python:0.0.5
    stdin_open: true
    tty: true
    volumes:
      - ~/w205:/w205
    expose:
      - "8888"
    ports:
      - "8888:8888"
    extra_hosts:
      - "moby:127.0.0.1"
    command: bash

  mids:
    image: midsw205/base:0.1.8
    stdin_open: true
    tty: true
    volumes:
      - ~/w205:/w205
    expose:
      - "5000"
    ports:
      - "5000:5000"
    extra_hosts:
      - "moby:127.0.0.1"

```
The difference for this week is that we now have a Spark image in the cluster.

## Update the images
```
docker pull confluentinc/cp-zookeeper:latest
docker pull confluentinc/cp-kafka:latest
docker pull midsw205/spark-python:0.0.5
docker pull midsw205/base:0.1.8
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
I exec into a mids bash and create `game_api_with_json_events.py`
```python
#!/usr/bin/env python
import json
from kafka import KafkaProducer
from flask import Flask

app = Flask(__name__)
producer = KafkaProducer(bootstrap_servers='kafka:29092')


def log_to_kafka(topic, event):
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
Instead of a simple string, we now encode a Python dictionary when logging to Kafka.

## Start the Flask app
```
docker-compose exec mids env FLASK_APP=/w205/assignment-10-hougrammer/game_api_with_json_events.py flask run
```
The terminal is now running `game_api_with_json_events` localhost port 5000
```
 * Serving Flask app "game_api_with_json_events"
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
127.0.0.1 - - [07/Jul/2018 23:38:58] "GET / HTTP/1.1" 200 -
127.0.0.1 - - [07/Jul/2018 23:39:09] "GET /purchase_a_sword HTTP/1.1" 200 -
```

## Check the Kafka topic
```
docker-compose exec mids bash -c "kafkacat -C -b kafka:29092 -t events -o beginning -e"
```
```
{"event_type": "default"}
{"event_type": "purchase_sword"}
% Reached end of topic events [0] at offset 2: exiting
```
As expected, we have two events in the topic.  They are both in a format that can be easily read as JSON.

## Enhance the logged JSON objects
I exec into a mids bash and create `game_api_with_extended_json_events.py`
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
In addition to `event_type`, we are also including the HTTP header in the dump to Kafka.

## Start the new Flask app
I stop the first Flask app and start the new one.  Note that I did not tear down the cluster, so the Kafka topic persists.
```
docker-compose exec mids env FLASK_APP=/w205/assignment-10-hougrammer/game_api_with_extended_json_events.py flask run
```
The terminal is now running `game_api_with_extended_json_events.py` localhost port 5000
```
 * Serving Flask app "game_api_with_extended_json_events.py"
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

## Make more calls to the API
Using another terminal, I run the following commands again.
```
docker-compose exec mids curl http://localhost:5000/
docker-compose exec mids curl http://localhost:5000/purchase_a_sword
```

## Check the Kafka topic again
```
docker-compose exec mids bash -c "kafkacat -C -b kafka:29092 -t events -o beginning -e"
```
```
{"event_type": "default"}
{"event_type": "purchase_sword"}
{"event_type": "default"}
{"event_type": "purchase_sword"}
{"Host": "localhost:5000", "event_type": "default", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
{"Host": "localhost:5000", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent": "curl/7.47.0"}
% Reached end of topic events [0] at offset 6: exiting
```
The Kafka topic contains messages of both APIs.  The bottom ones show the HTTP header as expected.

## Start Spark
```
docker-compose exec spark pyspark
```
The following sections are run in PySpark.

### Read the Kafka Topic
```
raw_events = spark \
  .read \
  .format("kafka") \
  .option("kafka.bootstrap.servers", "kafka:29092") \
  .option("subscribe","events") \
  .option("startingOffsets", "earliest") \
  .option("endingOffsets", "latest") \
  .load() 
```

### Cache the RDD
```
raw_events.cache()
```

### Cast the values to strings
```
events = raw_events.select(raw_events.value.cast('string'))
```

### Extract the values as JSON
```
import json
extracted_events = events.rdd.map(lambda x: json.loads(x.value)).toDF()
```

### Show the extracted events
```
extracted_events.show()
```

|    event_type|
|--------------|
|       default|
|purchase_sword|
|       default|
|purchase_sword|
|       default|
|purchase_sword|

Note that Spark could not infer the schema of the events with the enhanced API.  This is because the first few events only had `event_type` as a parameter.

### End of Spark Section

## Enhance the API further
I make a `game_api.py`
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
We now have a `purchase_item` method which only accepts swords and knives.  We also have a `join_guild` method which accept integer guild IDs.

## Test the enhanced API
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
And I run it with `python3 api_tests.py`
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

## Tear down the cluster
```
docker-compose down
```

## Summary
This week we created a simple Flask app to handle API calls to a mobile game's server.  We showed that the API could properly log the events to a Kafka queue.

## Enhancements
* Changed `purchase_a_sword` to `purchase_item` which accepts an item parameter
* Implemented `join_guild` which accepts a guild ID
