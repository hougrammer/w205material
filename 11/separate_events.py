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
    munged_events.show()

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
