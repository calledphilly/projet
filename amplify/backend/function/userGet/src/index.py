import json
import boto3
import os
import re
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
USERS_TABLE = os.environ.get('USERS_TABLE', 'users-dev')
EMAIL_INDEX = 'email'


def get(event, context):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Allow-Methods': '*',
    }

    try:
        query_params = event.get('queryStringParameters') or {}
        email = query_params.get('email', '').strip()

        if not email:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Email query parameter is required'})
            }

        if not is_valid_email(email):
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Invalid email format'})
            }

        table = dynamodb.Table(USERS_TABLE)

        response = table.query(
            IndexName=EMAIL_INDEX,
            KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(email)
        )

        if response.get('Count', 0) == 0:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'User not found'})
            }

        user = response['Items'][0]
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(user)
        }

    except ClientError as e:
        print("DynamoDB error:", e)
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Database error: ' + str(e)})
        }
    except Exception as e:
        print("Unhandled exception:", e)
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Internal server error'})
        }


def is_valid_email(email):
    if not email or '@' not in email:
        return False
    try:
        local, domain = email.rsplit('@', 1)
    except ValueError:
        return False
    if not local or len(local) > 64:
        return False
    if not domain or len(domain) > 255:
        return False
    if '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        return False
    if '..' in email:
        return False
    local_pattern = r'^[a-zA-Z0-9._%+-]+$'
    if not re.match(local_pattern, local):
        return False
    domain_pattern = r'^[a-zA-Z0-9.-]+$'
    if not re.match(domain_pattern, domain):
        return False
    domain_parts = domain.split('.')
    if len(domain_parts) < 2:
        return False
    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False
    for part in domain_parts:
        if not part:
            return False
    return True