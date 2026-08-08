import json
import os
import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

ddb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

PEOPLE_TABLE = ddb.Table(os.environ["PEOPLE_TABLE"])
APPEARANCES_TABLE = ddb.Table(os.environ["APPEARANCES_TABLE"])

THUMBS_BUCKET = os.environ["PROCESSED_BUCKET"]
RAW_BUCKET = os.environ["RAW_BUCKET"]
PRESIGN_EXPIRY_SECONDS = 3600  # how long each presigned URL stays valid


def _json_default(o):
    if isinstance(o, Decimal):
        if o % 1 == 0:
            return int(o)
        return float(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body, default=_json_default),
    }


def _presign_get(bucket: str, key: str):
    if not key:
        return None
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=PRESIGN_EXPIRY_SECONDS,
    )


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod")
    path = event.get("rawPath") or event.get("path") or ""

    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    if method == "GET" and path == "/people":
        return list_people()

    if method == "GET" and path.startswith("/people/") and path.endswith("/photos"):
        parts = path.strip("/").split("/")
        if len(parts) != 3:
            return _resp(400, {"error": "bad path"})
        person_id = parts[1]
        return list_photos_for_person(person_id)

    if method == "POST" and path == "/uploads":
        return create_upload_url(event)

    return _resp(404, {"error": "not found", "path": path})


def list_people():
    items = []
    resp = PEOPLE_TABLE.scan(Limit=200)
    items.extend(resp.get("Items", []))

    while "LastEvaluatedKey" in resp and len(items) < 200:
        resp = PEOPLE_TABLE.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], Limit=200)
        items.extend(resp.get("Items", []))

    items.sort(key=lambda x: int(x.get("photoCount", 0)), reverse=True)

    people = []
    for item in items[:100]:
        people.append({
            "personId": item.get("person_id"),
            "photoCount": item.get("photoCount", 0),
            "thumbnailUrl": _presign_get(THUMBS_BUCKET, item.get("repThumbKey")),
        })

    return _resp(200, {"people": people})


def list_photos_for_person(person_id: str):
    appearances = APPEARANCES_TABLE.query(
        KeyConditionExpression=Key("person_id").eq(person_id),
        Limit=200
    ).get("Items", [])

    photos = []
    for appearance in appearances:
        photo_id = appearance.get("photo_id")
        if not photo_id:
            continue

        photos.append({
            "photoId": photo_id,
            "thumbnailUrl": _presign_get(THUMBS_BUCKET, appearance.get("thumbKey")),
            "confidence": appearance.get("confidence"),
        })

    return _resp(200, {"personId": person_id, "photos": photos})


def create_upload_url(event):
    # Client tells us the filename it wants to upload; we generate a
    # unique key so concurrent/repeat uploads never collide, and hand
    # back a presigned PUT URL. The client then uploads the file bytes
    # directly to S3 -- never through this Lambda or API Gateway, which
    # avoids their payload size limits (10MB / 6MB respectively).
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid JSON body"})

    filename = body.get("filename", "upload.jpg")
    extension = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    upload_key = f"{uuid.uuid4()}.{extension}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": RAW_BUCKET, "Key": upload_key, "ContentType": "image/jpeg"},
        ExpiresIn=PRESIGN_EXPIRY_SECONDS,
    )

    return _resp(200, {
        "uploadUrl": upload_url,
        "key": upload_key,
        "bucket": RAW_BUCKET,
    })