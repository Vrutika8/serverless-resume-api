"""Lambda handler for the Resume API.

Each GET route returns one section of the resume. Data is read from the
DynamoDB table; if a section is missing there, the bundled ``resume.json``
file is used as a fallback so the API always has something to serve.
"""
import json
import logging
import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

DATA_FILE = Path(__file__).with_name("resume.json")
KEY_ATTRIBUTES = ("section", "itemId")
SINGLE_ITEM_SECTIONS = {"personal"}
SECTION_ROUTES = {
    "/personal": "personal",
    "/experience": "experience",
    "/education": "education",
    "/skills": "skills",
}
HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "max-age=300",
}

_table = None


def get_table():
    """Create the DynamoDB table resource once per container (warm start reuse)."""
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


@lru_cache(maxsize=1)
def load_fallback_data():
    with DATA_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def query_section(section):
    """Return every item of a section, following DynamoDB pagination."""
    table = get_table()
    params = {"KeyConditionExpression": Key("section").eq(section)}
    items = []
    while True:
        result = table.query(**params)
        items.extend(result["Items"])
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return items
        params["ExclusiveStartKey"] = last_key


def get_section(section):
    """Return a section as a dict (personal) or a list (everything else)."""
    items = query_section(section)
    if not items:
        logger.warning("Section '%s' not found in DynamoDB; using resume.json", section)
        return load_fallback_data()[section]

    cleaned = [
        {key: value for key, value in item.items() if key not in KEY_ATTRIBUTES}
        for item in items
    ]
    return cleaned[0] if section in SINGLE_ITEM_SECTIONS else cleaned


def _json_default(value):
    """DynamoDB returns numbers as Decimal, which json cannot serialise."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": HEADERS,
        "body": json.dumps(body, default=_json_default),
    }


def lambda_handler(event, _context):
    resource = event.get("resource")
    try:
        if resource == "/resume":
            sections = set(SECTION_ROUTES.values())
            return build_response(200, {name: get_section(name) for name in sorted(sections)})

        section = SECTION_ROUTES.get(resource)
        if section is None:
            return build_response(404, {"message": "Not found"})
        return build_response(200, get_section(section))
    except ClientError:
        logger.exception("DynamoDB request failed")
        return build_response(500, {"message": "Internal server error"})
