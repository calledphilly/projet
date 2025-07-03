import json
import os
import uuid
import boto3

# dynamodb = boto3.resource("dynamodb")
# table = dynamodb.Table(os.environ["STORAGE_USERTABLE_NAME"])
TABLE_NAME = os.environ.get("STORAGE_USERTABLE_NAME", "users-dev")
dynamodb = boto3.resource("dynamodb", region_name="eu-west-1")
table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
  print('received event:')
  print(event)
  
  try:
    email = event.get("email", "{}")

    if not email:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'email' in request"})
        }

    id = str(uuid.uuid4())
    table.put_item(Item={"id": id, "email": email})
  
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
        'body': json.dumps('Hello from your new Amplify Python lambda!')
    }
  except Exception as e:
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }