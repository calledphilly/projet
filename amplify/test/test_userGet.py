import pytest
import json
import boto3
import os
import sys
from moto import mock_dynamodb
import uuid
import importlib.util

# Set environment variables for the lambda
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['USERS_TABLE'] = 'users-dev'

# Add the lambda source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'function', 'userGet', 'src'))

def import_get():
    import sys
    import os
    index_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'function', 'userGet', 'src', 'index.py')
    spec = importlib.util.spec_from_file_location("index", index_path)
    index = importlib.util.module_from_spec(spec)
    sys.modules["index"] = index
    spec.loader.exec_module(index)
    return index.get

class TestUserGet:

    def setup_method(self, method):
        self.get = import_get()

    def setup_table(self):
        dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
        table = dynamodb.create_table(
            TableName='users-dev',
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'email', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'email',
                'KeySchema': [{'AttributeName': 'email', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'},
                'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            }],
            BillingMode='PROVISIONED',
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        table.meta.client.get_waiter('table_exists').wait(TableName='users-dev')
        return table

    @mock_dynamodb
    def test_get_user_success(self):
        table = self.setup_table()
        test_user = {'id': str(uuid.uuid4()), 'email': 'test@example.com'}
        table.put_item(Item=test_user)

        event = {'queryStringParameters': {'email': 'test@example.com'}}
        response = self.get(event, {})
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body == test_user
        assert response['headers']['Access-Control-Allow-Origin'] == '*'

    @mock_dynamodb
    def test_get_user_not_found(self):
        self.setup_table()
        event = {'queryStringParameters': {'email': 'nonexistent@example.com'}}
        response = self.get(event, {})
        assert response['statusCode'] == 404
        assert json.loads(response['body']) == {'error': 'User not found'}

    @mock_dynamodb
    @pytest.mark.parametrize("query", [
        {}, {'email': ''}, {'email': '   '}, None
    ])
    def test_get_user_missing_or_invalid_email(self, query):
        self.setup_table()
        event = {'queryStringParameters': query}
        response = self.get(event, {})
        assert response['statusCode'] == 400
        assert json.loads(response['body']) == {'error': 'Email query parameter is required'}

    @mock_dynamodb
    def test_get_user_invalid_email_format(self):
        self.setup_table()
        invalid_emails = [
            'bademail', 'bad@email', 'bad@.com', '@example.com',
            'user@', 'user@domain', 'user..name@domain.com'
        ]
        for email in invalid_emails:
            event = {'queryStringParameters': {'email': email}}
            response = self.get(event, {})
            assert response['statusCode'] == 400
            assert json.loads(response['body']) == {'error': 'Invalid email format'}

    @mock_dynamodb
    def test_get_user_valid_email_formats_but_not_found(self):
        self.setup_table()
        valid_emails = [
            'user@example.com', 'test.email@domain.co.uk', 'user+tag@example.org',
            'user123@test-domain.com', 'a@b.co', 'firstname.lastname@example.com',
            'email@subdomain.example.com', 'user_name@example.co',
            'x@example.com'
        ]
        for email in valid_emails:
            event = {'queryStringParameters': {'email': email}}
            response = self.get(event, {})
            assert response['statusCode'] == 404
            assert json.loads(response['body']) == {'error': 'User not found'}

    @mock_dynamodb
    def test_get_user_case_sensitive_email(self):
        table = self.setup_table()
        test_user = {'id': str(uuid.uuid4()), 'email': 'test@example.com'}
        table.put_item(Item=test_user)

        event = {'queryStringParameters': {'email': 'TEST@EXAMPLE.COM'}}
        response = self.get(event, {})
        assert response['statusCode'] == 404
        assert json.loads(response['body']) == {'error': 'User not found'}

    @mock_dynamodb
    def test_cors_headers_present_in_all_cases(self):
        table = self.setup_table()
        table.put_item(Item={'id': str(uuid.uuid4()), 'email': 'test@example.com'})

        for event in [
            {'httpMethod': 'GET', 'queryStringParameters': {'email': 'test@example.com'}},
            {'httpMethod': 'POST'}
        ]:
            response = self.get(event, {})
            headers = response['headers']
            assert headers['Access-Control-Allow-Origin'] == '*'
            assert 'Access-Control-Allow-Headers' in headers
            assert 'Access-Control-Allow-Methods' in headers

    @mock_dynamodb
    def test_database_error_handling(self):
        table = self.setup_table()
        table.delete()
        event = {'httpMethod': 'GET', 'queryStringParameters': {'email': 'test@example.com'}}
        response = self.get(event, {})
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error'].startswith('Database error:')

    @mock_dynamodb
    def test_email_trimming(self):
        table = self.setup_table()
        test_user = {'id': str(uuid.uuid4()), 'email': 'test@example.com'}
        table.put_item(Item=test_user)
        event = {'httpMethod': 'GET', 'queryStringParameters': {'email': '  test@example.com  '}}
        response = self.get(event, {})
        assert response['statusCode'] == 200
        assert json.loads(response['body'])['email'] == 'test@example.com'

    @mock_dynamodb
    def test_multiple_users_same_email_returns_one(self):
        table = self.setup_table()
        test_user1 = {'id': str(uuid.uuid4()), 'email': 'test@example.com'}
        test_user2 = {'id': str(uuid.uuid4()), 'email': 'test@example.com'}
        table.put_item(Item=test_user1)
        table.put_item(Item=test_user2)
        event = {'httpMethod': 'GET', 'queryStringParameters': {'email': 'test@example.com'}}
        response = self.get(event, {})
        assert response['statusCode'] == 200
        returned = json.loads(response['body'])
        assert returned['email'] == 'test@example.com'
        assert returned['id'] in [test_user1['id'], test_user2['id']]