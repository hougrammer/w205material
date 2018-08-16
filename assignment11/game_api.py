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
