import json
import os
import re
import uuid

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
USERS_TABLE = os.environ.get('USERS_TABLE', 'users-dev')
EMAIL_INDEX = 'email'


def add(event, context):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Allow-Methods': '*',
    }

    try:
        if 'body' not in event or event['body'] is None:
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Request body is required'})}

        try:
            data = json.loads(event['body'])
        except (json.JSONDecodeError, TypeError):
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Invalid JSON in request body'})}

        email = data.get('email', '').strip()
        if not email:
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Email is required'})}

        # Get optional name field
        name = data.get('name', '').strip()

        # Strict email format validation
        if not is_valid_email(email):
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Invalid email format'})}

        # Validate name if provided
        if name and len(name) > 100:
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Name must be less than 100 characters'})}

        table = dynamodb.Table(USERS_TABLE)

        # Check for existing user with the same email
        existing = table.query(IndexName=EMAIL_INDEX, KeyConditionExpression=Key('email').eq(email))

        if existing.get('Count', 0) > 0:
            return {'statusCode': 409, 'headers': headers, 'body': json.dumps({'error': 'User with this email already exists'})}

        # Create new user
        user_id = str(uuid.uuid4())
        user = {'id': user_id, 'email': email}

        # Add name if provided
        if name:
            user['name'] = name

        table.put_item(Item=user)

        return {'statusCode': 201, 'headers': headers, 'body': json.dumps(user)}

    except ClientError as e:
        print("DynamoDB error:", e)
        return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': 'Database error: ' + str(e)})}
    except Exception as e:
        print("Unhandled exception:", e)
        return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': 'Internal server error'+ str(e)})}


def is_valid_email(email):
    """
    Validate email format with strict rules
    """
    # Basic structure check
    if not email or '@' not in email:
        return False

    # Split into local and domain parts
    try:
        local, domain = email.rsplit('@', 1)
    except ValueError:
        return False

    # Check local part (before @)
    if not local or len(local) > 64:
        return False

    # Check domain part (after @)
    if not domain or len(domain) > 255:
        return False

    # Domain must contain at least one dot
    if '.' not in domain:
        return False

    # Domain cannot start or end with dot
    if domain.startswith('.') or domain.endswith('.'):
        return False

    # Check for consecutive dots
    if '..' in email:
        return False

    # Check for valid characters in local part
    local_pattern = r'^[a-zA-Z0-9._%+-]+$'
    if not re.match(local_pattern, local):
        return False

    # Check for valid characters in domain part
    domain_pattern = r'^[a-zA-Z0-9.-]+$'
    if not re.match(domain_pattern, domain):
        return False

    # Domain must have at least one part after the last dot (TLD)
    domain_parts = domain.split('.')
    if len(domain_parts) < 2:
        return False

    # Last part (TLD) must be at least 2 characters and only letters
    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False

    # Domain parts cannot be empty
    for part in domain_parts:
        if not part:
            return False

    return True
