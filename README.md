# ELK Stack Deployment with Docker

## Overview

This project provides a minimal and reproducible deployment of the ELK stack (Elasticsearch, Logstash, Kibana) using Docker Compose. Authentication is enabled and the setup follows standard software engineering and DevOps best practices.

* **ELK Version:** 7.14
* **Deployment:** Docker Compose
* **Security:** X-Pack enabled

## Prerequisites

* Linux or macOS environment
* Docker
* Docker Compose
* Git
* Internet access

## Project Structure

```
.
├── docker-compose.yml
├── logstash/
│   └── pipeline/
│       └── logstash.conf
└── README.md
```

## Step 1 — ELK Stack Installation

The stack consists of three services:

* **Elasticsearch** – search and storage engine
* **Logstash** – data ingestion and processing
* **Kibana** – visualization interface

All services run on a dedicated Docker bridge network. Elasticsearch data is persisted using a Docker volume.

### Start the Stack

From the project root:

```bash
docker compose up -d
```

### Access Endpoints

* **Elasticsearch:** http://localhost:9200
* **Kibana:** http://localhost:5601

## Step 2 — Authentication Configuration

Authentication is enabled using X-Pack Security, included by default in Elasticsearch 7.14.

### Elasticsearch

* X-Pack security is enabled
* A predefined superuser (`elastic`) is configured at startup

### Kibana

Kibana authenticates against Elasticsearch using secured credentials.

**Login credentials:**

* **Username:** elastic
* **Password:** elastic

Successful authentication grants access to the Kibana interface.