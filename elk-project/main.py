import os
from elasticsearch import Elasticsearch
import pandas as pd


def main():
    print("Pandas version:", pd.__version__)

    es_url = os.getenv("ELASTICSEARCH_URL")
    api_key = os.getenv("ELASTIC_API_KEY")

    if not es_url or not api_key:
        raise RuntimeError(
            "Missing ELASTICSEARCH_URL or ELASTIC_API_KEY environment variables"
        )

    client = Elasticsearch(
        hosts=[es_url],
        api_key=api_key,
    )

    resp = client.search(
        index="my-index-000001",
        from_=40,
        size=20,
        query={
            "term": {
                "user.id": "kimchy"
            }
        },
    )

    print(resp)


if __name__ == "__main__":
    main()
