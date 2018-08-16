#!/usr/bin/env python
from kafka import KafkaProducer
from flask import Flask
from flask import request

app = Flask(__name__)
event_logger = KafkaProducer(bootstrap_servers='kafka:29092')
events_topic = 'events'

@app.route("/")
def default_response():
    event_logger.send(events_topic, 'default'.encode())
    return "\nThis is the default response!\n"

@app.route("/purchase_a_sword")
def purchase_sword():
    event_logger.send(events_topic, 'purchased_sword'.encode())
    return "\nSword Purchased!\n"

@app.route("/purchase_a_knife")
def purchase_knife():
    event_logger.send(events_topic, 'purchased_knife'.encode())
    return "\nKnife Purchased!\n"

@app.route("/join_a_guild")
def join_guild():
    try:
        guild_id = request.args.get('guild_id')
        event_logger.send(events_topic, ('joined_guild %d' % int(guild_id)).encode())
        return "\nJoined Guild %d!\n" % int(guild_id)
    except:
        event_logger.send(events_topic, 'missing_guild_id'.encode())
        return "\nMissing Guild ID!\n"
