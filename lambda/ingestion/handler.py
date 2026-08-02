import json


def lambda_handler(event, context):
    """
    Triggered automatically by S3 when a new photo is uploaded to the raw bucket.
    'event' contains details about which bucket/file triggered this.
    For now this just logs the event so we can confirm the trigger wiring works.
    """
    print("Received event:")
    print(json.dumps(event, indent=2))

    # Every S3 trigger event can technically contain multiple records
    # (e.g. if you upload many files fast), so we loop through them
    for record in event["Records"]:
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = record["s3"]["object"]["key"]
        print(f"New photo uploaded: s3://{bucket_name}/{object_key}")

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Event received"})
    }