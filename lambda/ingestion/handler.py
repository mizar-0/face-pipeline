import json
import os
import hashlib
from datetime import datetime, timezone
from urllib.parse import unquote_plus
from io import BytesIO
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from PIL import Image

ddb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
rek = boto3.client("rekognition")

PHOTOS_TABLE_NAME = os.environ["PHOTOS_TABLE"]
THUMBS_BUCKET = os.environ["PROCESSED_BUCKET"]
THUMBS_PREFIX = "faces-thumbs/"
PEOPLE_TABLE_NAME = os.environ.get("PEOPLE_TABLE")
APPEARANCES_TABLE_NAME = os.environ.get("APPEARANCES_TABLE")

collection_id = os.environ["REKOGNITION_COLLECTION"]
threshold = float(os.environ.get("FACE_MATCH_THRESHOLD", "95"))

photos_table = ddb.Table(PHOTOS_TABLE_NAME)
people_table = ddb.Table(PEOPLE_TABLE_NAME)
appearances_table = ddb.Table(APPEARANCES_TABLE_NAME)


def make_photo_id(bucket: str, key: str) -> str:
    raw = f"{bucket}/{key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def bbox_to_pixels(bbox: dict, img_w: int, img_h: int):
    left = clamp01(float(bbox.get("Left", 0.0)))
    top = clamp01(float(bbox.get("Top", 0.0)))
    width = float(bbox.get("Width", 0.0))
    height = float(bbox.get("Height", 0.0))

    right = clamp01(left + width)
    bottom = clamp01(top + height)

    x1 = int(left * img_w)
    y1 = int(top * img_h)
    x2 = int(right * img_w)
    y2 = int(bottom * img_h)

    x2 = max(x2, x1 + 1)
    y2 = max(y2, y1 + 1)
    return x1, y1, x2, y2


def as_decimal_bbox(bbox: dict) -> dict:
    return {
        "Left": Decimal(str(bbox.get("Left", 0.0))),
        "Top": Decimal(str(bbox.get("Top", 0.0))),
        "Width": Decimal(str(bbox.get("Width", 0.0))),
        "Height": Decimal(str(bbox.get("Height", 0.0))),
    }

def upsert_person(person_id: str, rep_thumb_key: str, created_at: str):
    people_table.update_item(
        Key={"person_id": person_id},
        UpdateExpression=(
            "SET createdAt = if_not_exists(createdAt, :ca), "
            "repThumbKey = if_not_exists(repThumbKey, :rt) "
            "ADD photoCount :inc"
        ),
        ExpressionAttributeValues={
            ":ca": created_at,
            ":rt": rep_thumb_key,
            ":inc": Decimal(1),
        },
    )

def write_appearance(
    person_id: str,
    photo_id: str,
    photo_bucket: str,
    photo_key: str,
    thumb_key: str,
    bbox: dict,
    confidence: float | None,
):
    item = {
        "person_id": person_id,
        "photo_id": photo_id,
        "photoBucket": photo_bucket,
        "photoKey": photo_key,
        "thumbKey": thumb_key,
        "boundingBox": as_decimal_bbox(bbox),
        "confidence": confidence
    }
    if confidence is not None:
        item["confidence"] = Decimal(str(confidence))

    appearances_table.put_item(Item=item)


def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        print("No Records in event; exiting.")
        return {"statusCode": 200, "body": "no records"}

    for record in records:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        key = s3_info.get("object", {}).get("key")

        if not bucket or not key:
            print("Skipping record: missing bucket/key")
            continue

        key = unquote_plus(key)
        photo_id = make_photo_id(bucket, key)
        uploaded_at = datetime.now(timezone.utc).isoformat()

        item = {
            "photo_id": photo_id,
            "source_bucket": bucket,
            "source_key": key,
            "uploaded_at": uploaded_at,
        }

        try:
            photos_table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(photo_id)",
            )
            print(f"Photos: inserted photo_id={photo_id} key={key}")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            if code == "ConditionalCheckFailedException":
                print(f"Photos: already exists; skipping photo_id={photo_id} key={key}")
                continue
            print("DynamoDB put_item failed:", str(e))
            raise

        # Full image is referenced via S3Object -- safe regardless of size,
        # since Rekognition fetches it directly, no 5MB inline limit here
        resp = rek.detect_faces(
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            Attributes=["DEFAULT"],
        )

        face_details = resp.get("FaceDetails", [])
        face_count = len(face_details)
        print(f"DetectFaces: photo_id={photo_id} faces={face_count}")

        photos_table.update_item(
            Key={"photo_id": photo_id},
            UpdateExpression="SET face_count = :c",
            ExpressionAttributeValues={":c": face_count},
        )

        if face_count == 0:
            print(f"No faces; done for photo_id={photo_id}")
            continue

        obj = s3.get_object(Bucket=bucket, Key=key)
        img_bytes = obj["Body"].read()

        im = Image.open(BytesIO(img_bytes)).convert("RGB")
        img_w, img_h = im.size
        print(f"Image: photo_id={photo_id} size={img_w}x{img_h}")

        thumb_keys = []

        for idx, fd in enumerate(face_details, start=1):
            bbox = fd.get("BoundingBox", {})
            confidence = fd.get("Confidence") 
            x1, y1, x2, y2 = bbox_to_pixels(bbox, img_w, img_h)

            face_im = im.crop((x1, y1, x2, y2))
            out = BytesIO()
            face_im.save(out, format="JPEG", quality=90)
            out.seek(0)
            face_bytes = out.getvalue()

            # This is a small, already-cropped face -- safely under the
            # 5MB inline Bytes limit, and it only exists in memory so
            # there's no S3Object to reference yet.
            search_resp = rek.search_faces_by_image(
                CollectionId=collection_id,
                Image={"Bytes": face_bytes},
                MaxFaces=1,
                FaceMatchThreshold=threshold,
            )

            matches = search_resp.get("FaceMatches", [])
            if matches:
                top_match = matches[0]
                person_id = top_match["Face"]["FaceId"]
                similarity = top_match.get("Similarity")
                print(f"Match: idx={idx} person_id={person_id} similarity={similarity}")
            else:
                print(f"NoMatch: idx={idx} threshold={threshold} -> indexing")
                index_resp = rek.index_faces(
                    CollectionId=collection_id,
                    Image={"Bytes": face_bytes},
                    ExternalImageId=f"{photo_id}_face_{idx}",
                    MaxFaces=1,
                    DetectionAttributes=["DEFAULT"],
                )

                face_records = index_resp.get("FaceRecords", [])
                if not face_records:
                    print("IndexFaces failed; UnindexedFaces=", index_resp.get("UnindexedFaces", []))
                    continue

                person_id = face_records[0]["Face"]["FaceId"]
                print(f"Indexed: idx={idx} new person_id={person_id}")

            thumb_key = f"{THUMBS_PREFIX}{person_id}/{photo_id}_face_{idx}.jpg"
            s3.put_object(
                Bucket=THUMBS_BUCKET,
                Key=thumb_key,
                Body=face_bytes,
                ContentType="image/jpeg",
            )
            thumb_keys.append(thumb_key)

            # increment photoCount (for "most frequent" People grid)
            # set repThumbKey once
            upsert_person(
                person_id=person_id,
                rep_thumb_key=thumb_key,
                created_at=uploaded_at,
            )

            # record that this person appears in this photo
            write_appearance(
                person_id=person_id,
                photo_id=photo_id,
                photo_bucket=bucket,
                photo_key=key,
                thumb_key=thumb_key,
                bbox=bbox,
                confidence=confidence,
            )

        print(f"Thumbnails: uploaded {len(thumb_keys)} for photo_id={photo_id}")
        print(f"Wrote Persons/Appearances for photoId={photo_id}")

        photos_table.update_item(
            Key={"photo_id": photo_id},
            UpdateExpression="SET face_thumb_keys = :k",
            ExpressionAttributeValues={":k": thumb_keys},
        )
        print(f"Updated Photos table with thumb_keys: {thumb_keys}")

    return {"statusCode": 200, "body": json.dumps({"message": "ok"})}