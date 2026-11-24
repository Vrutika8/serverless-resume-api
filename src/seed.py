"""CloudFormation custom resource that loads resume.json into DynamoDB."""
import json
import logging
import os
import urllib.request
from decimal import Decimal
from pathlib import Path

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DATA_FILE = Path(__file__).with_name("resume.json")
LIST_SECTIONS = ("experience", "education", "skills")


def build_items(data):
    """Convert resume.json into DynamoDB items (partition key: section, sort key: itemId)."""
    items = [{"section": "personal", "itemId": "profile", **data["personal"]}]
    for section in LIST_SECTIONS:
        for index, entry in enumerate(data[section], start=1):
            items.append({"section": section, "itemId": f"{index:03d}", **entry})
    return items


def scan_keys(table):
    params = {"ProjectionExpression": "#s, itemId", "ExpressionAttributeNames": {"#s": "section"}}
    while True:
        result = table.scan(**params)
        for item in result["Items"]:
            yield item["section"], item["itemId"]
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return
        params["ExclusiveStartKey"] = last_key


def seed_table(table, data):
    """Write all items, then delete any stale items left from a previous version."""
    items = build_items(data)
    new_keys = {(item["section"], item["itemId"]) for item in items}

    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    stale_keys = [key for key in scan_keys(table) if key not in new_keys]
    with table.batch_writer() as batch:
        for section, item_id in stale_keys:
            batch.delete_item(Key={"section": section, "itemId": item_id})

    logger.info("Seeded %d items, removed %d stale items", len(items), len(stale_keys))


def send_response(event, context, status, reason=""):
    """Report the result back to CloudFormation (required for custom resources)."""
    body = json.dumps({
        "Status": status,
        "Reason": reason or f"See CloudWatch log stream: {context.log_stream_name}",
        "PhysicalResourceId": event.get("PhysicalResourceId") or "ResumeDataSeed",
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "Data": {},
    }).encode("utf-8")
    request = urllib.request.Request(
        event["ResponseURL"], data=body, method="PUT",
        headers={"Content-Type": "", "Content-Length": str(len(body))},
    )
    with urllib.request.urlopen(request, timeout=10):
        pass


def lambda_handler(event, context):
    try:
        if event["RequestType"] in ("Create", "Update"):
            with DATA_FILE.open(encoding="utf-8") as file:
                data = json.load(file, parse_float=Decimal)  # DynamoDB rejects float
            table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
            seed_table(table, data)
        send_response(event, context, "SUCCESS")
    except Exception as exc:  # report every failure, otherwise the stack hangs
        logger.exception("Seeding failed")
        send_response(event, context, "FAILED", str(exc))
