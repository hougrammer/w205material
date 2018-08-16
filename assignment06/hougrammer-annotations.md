# My annotations, Assignment 6


##  303  cd w205/assignment-06-hougrammer/.
Change into the directory for the assignment 6 git repo I cloned already.  Inside the mids container, I had already created a `docker-compose.yml` file with the below configuration.  Those commands were not written to history because they were in a another bash session.
```yml
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
    #ports:
      #- "32181:32181"
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
    volumes:
      - ~/w205:/w205
    expose:
      - "9092"
      - "29092"
    extra_hosts:
      - "moby:127.0.0.1"

  mids:
    image: midsw205/base:latest
    stdin_open: true
    tty: true
    volumes:
      - ~/w205:/w205
    extra_hosts:
      - "moby:127.0.0.1"
```
I had also run curl to get the json file into the github repo.
```bash
curl -L -o assessment-attempts-20180128-121051-nested.json https://goo.gl/f5bRm4
```

##  304  git status
Check on the status of git to see that I'm still on the assignment branch.

##  308  docker-compose up -d
Start the docker cluster in detached mode.

##  309  docker-compose logs -f kafka
Check the kafka logs with the follow flag to see what was being written.  Nothing is writing to Kafka, so use control C to break back out.

##  311  head assessment-attempts-20180128-121051-nested.json 
Used head to try to check beginning of the json file.  A lot wrote to the terminal since there is only one line.

##  312  docker-compose exec kafka     kafka-topics       --create       --topic foo       --partitions 1       --replication-factor 1
Create a Kafka topic called "foo" with 1 partition and 1 replication.

##  313  docker-compose exec kafka   kafka-topics     --describe     --topic foo     --zookeeper zookeeper:32181
Describe the kafka-topic we just created

```
Topic:foo       PartitionCount:1        ReplicationFactor:1     Configs:
        Topic: foo      Partition: 0    Leader: 1       Replicas: 1     Isr: 1
```

##  315  docker-compose exec mids bash -c "cat /w205/assignment-06-hougrammer/assessment-attempts-20180128-121051-nested.json | jq '.[]' -c | kafkacat -P -b kafka:29092 -t foo && echo 'Produced 100 messages.'"
Use the mids container to cat the json file into jq.  Using jq, retrieve all the first level array items in a compact format. Finally using kafkacat, the items to foo and echo a success message.

##  317  history > hougrammer-history.txt
Try to write the history but realize that only the mids container has write priveleges to the git repo.

##  325  cd w205/
Change to a directory with write privileges.

##  327  history > hougrammer-history.txt
Write history to a text file.

##  329  docker cp hougrammer-history.txt assignment06hougrammer_mids_1:/w205
Use docker cp to copy the text file into the mids container.

##  332  docker-compose exec mids bash
Open a bash session on the mids container and move the text file into the assignment 6 directory.

##  333  docker-compose exec mids bash -c "kafkacat -C -b kafka:29092 -t foo -o beginning -e"
Use kafkacat in the mids container to retrieve the message in foo.  A large amount of text writes to the terminal

##  334  docker-compose exec mids bash -c "kafkacat -C -b kafka:29092 -t foo -o beginning -e | wc -l" 
Use word count with the previous command to find the number of lines written.  There are 3280.

##  335  docker-compose down
Tear down the cluster.
