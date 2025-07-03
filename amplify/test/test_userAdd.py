import importlib.util
import json
import os
import sys
import uuid

import boto3
import pytest
from moto import mock_dynamodb

# Set environment variables for the lambda
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['USERS_TABLE'] = 'users-dev'


def import_add():
    import os
    import sys
    index_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'function', 'userAdd', 'src', 'index.py')
    spec = importlib.util.spec_from_file_location("index", index_path)
    index = importlib.util.module_from_spec(spec)
    sys.modules["index"] = index
    spec.loader.exec_module(index)
    return index.add


class TestUserAdd:

    def setup_method(self, method):
        self.add = import_add()

    def setup_table(self):
        """Helper to create the mock DynamoDB users table"""
        dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
        table = dynamodb.create_table(TableName='users-dev',
                                      KeySchema=[{
                                          'AttributeName': 'id',
                                          'KeyType': 'HASH'
                                      }],
                                      AttributeDefinitions=[{
                                          'AttributeName': 'id',
                                          'AttributeType': 'S'
                                      }, {
                                          'AttributeName': 'email',
                                          'AttributeType': 'S'
                                      }],
                                      GlobalSecondaryIndexes=[{
                                          'IndexName': 'email',
                                          'KeySchema': [{
                                              'AttributeName': 'email',
                                              'KeyType': 'HASH'
                                          }],
                                          'Projection': {
                                              'ProjectionType': 'ALL'
                                          },
                                          'ProvisionedThroughput': {
                                              'ReadCapacityUnits': 5,
                                              'WriteCapacityUnits': 5
                                          }
                                      }],
                                      BillingMode='PROVISIONED',
                                      ProvisionedThroughput={
                                          'ReadCapacityUnits': 5,
                                          'WriteCapacityUnits': 5
                                      })
        table.meta.client.get_waiter('table_exists').wait(TableName='users-dev')
        return table

    @mock_dynamodb
    def test_create_user_success(self):
        """Test successful user creation with proper validation"""
        self.table = self.setup_table()

        add = self.add

        event = {'body': json.dumps({'email': 'test@example.com'})}

        response = add(event, {})

        # Assert response structure
        assert response['statusCode'] == 201
        assert 'headers' in response
        assert 'body' in response

        # Assert CORS headers
        assert response['headers']['Access-Control-Allow-Origin'] == '*'

        # Assert body content
        body = json.loads(response['body'])
        assert 'id' in body
        assert body['email'] == 'test@example.com'
        assert len(body['id']) == 36  # UUID length

        # Verify user was actually created in DynamoDB
        created = self.table.get_item(Key={'id': body['id']})
        assert 'Item' in created
        assert created['Item']['email'] == 'test@example.com'
        assert created['Item']['id'] == body['id']

    @mock_dynamodb
    def test_create_user_missing_email(self):
        """Test missing email validation"""
        self.setup_table()
        add = self.add

        event = {'body': json.dumps({})}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Email is required'

    @mock_dynamodb
    def test_create_user_empty_email(self):
        """Test empty email validation"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST', 'body': json.dumps({'email': ''})}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Email is required'

    @mock_dynamodb
    def test_create_user_whitespace_email(self):
        """Test whitespace-only email validation"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST', 'body': json.dumps({'email': '   '})}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Email is required'

    @mock_dynamodb
    def test_create_user_invalid_email_format(self):
        """Test invalid email format validation"""
        self.setup_table()
        add = self.add

        invalid_emails = ['bademail', 'bad@email', 'bad@.com', '@example.com', 'user@', 'user@domain', 'user..name@domain.com']

        for invalid_email in invalid_emails:
            event = {'httpMethod': 'POST', 'body': json.dumps({'email': invalid_email})}
            response = add(event, {})
            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert body['error'] == 'Invalid email format'

    @mock_dynamodb
    def test_create_user_valid_email_formats(self):
        """Test various valid email formats"""
        self.setup_table()
        add = self.add

        valid_emails = ['user@example.com', 'test.email@domain.co.uk', 'user+tag@example.org', 'user123@test-domain.com', 'a@b.co']

        for valid_email in valid_emails:
            event = {'httpMethod': 'POST', 'body': json.dumps({'email': valid_email})}
            response = add(event, {})
            assert response['statusCode'] == 201
            body = json.loads(response['body'])
            assert body['email'] == valid_email

    @mock_dynamodb
    def test_create_user_duplicate_email(self):
        """Test duplicate email rejection"""
        self.table = self.setup_table()
        add = self.add

        # Insert existing user
        existing_email = 'existing@example.com'
        self.table.put_item(Item={'id': str(uuid.uuid4()), 'email': existing_email})

        event = {'httpMethod': 'POST', 'body': json.dumps({'email': existing_email})}
        response = add(event, {})

        assert response['statusCode'] == 409
        body = json.loads(response['body'])
        assert body['error'] == 'User with this email already exists'

    @mock_dynamodb
    def test_create_user_duplicate_email_case_sensitive(self):
        """Test that email comparison is case-sensitive"""
        self.table = self.setup_table()
        add = self.add

        # Insert existing user with lowercase email
        self.table.put_item(Item={'id': str(uuid.uuid4()), 'email': 'test@example.com'})

        # Try to create user with uppercase email - should succeed (case sensitive)
        event = {'httpMethod': 'POST', 'body': json.dumps({'email': 'TEST@EXAMPLE.COM'})}
        response = add(event, {})

        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['email'] == 'TEST@EXAMPLE.COM'

    @mock_dynamodb
    def test_create_user_invalid_json(self):
        """Test invalid JSON handling"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST', 'body': 'invalid json'}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Invalid JSON in request body'

    @mock_dynamodb
    def test_create_user_no_body(self):
        """Test missing body handling"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST'}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Request body is required'

    @mock_dynamodb
    def test_create_user_null_body(self):
        """Test null body handling"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST', 'body': None}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Request body is required'

    @mock_dynamodb
    def test_create_user_with_name(self):
        """Test user creation with name field"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST', 'body': json.dumps({'email': 'test@example.com', 'name': 'Jean Dupont'})}

        response = add(event, {})
        assert response['statusCode'] == 201

        body = json.loads(response['body'])
        assert body['email'] == 'test@example.com'
        assert body['name'] == 'Jean Dupont'
        assert 'id' in body

    @mock_dynamodb
    def test_create_user_name_too_long(self):
        """Test name length validation"""
        self.setup_table()
        add = self.add

        long_name = 'A' * 101  # 101 characters
        event = {'httpMethod': 'POST', 'body': json.dumps({'email': 'test@example.com', 'name': long_name})}

        response = add(event, {})
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Name must be less than 100 characters'

    @mock_dynamodb
    def test_create_user_additional_fields_ignored(self):
        """Test that self.additional fields are ignored for security"""
        self.setup_table()
        add = self.add

        event = {
            'httpMethod':
                'POST',
            'body':
                json.dumps({
                    'email': 'test@example.com',
                    'name': 'Test User',
                    'age': 42,
                    'admin': True,
                    'password': 'secret',
                    'extra': 'data'
                })
        }

        response = add(event, {})
        assert response['statusCode'] == 201

        body = json.loads(response['body'])
        assert body['email'] == 'test@example.com'
        assert body['name'] == 'Test User'  # Name should be kept
        assert 'age' not in body
        assert 'admin' not in body
        assert 'password' not in body
        assert 'extra' not in body

        # Verify only allowed fields are stored
        assert len(body) == 3  # 'id', 'email', and 'name'

    @mock_dynamodb
    def test_cors_headers_present(self):
        """Test CORS headers are present in all responses"""
        self.setup_table()
        add = self.add

        # Test success case
        event = {'body': json.dumps({'email': 'test@example.com'})}
        response = add(event, {})
        headers = response['headers']
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Headers' in headers
        assert 'Access-Control-Allow-Methods' in headers

        # Test error case (missing body)
        event = {}
        response = add(event, {})
        headers = response['headers']
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'Access-Control-Allow-Headers' in headers
        assert 'Access-Control-Allow-Methods' in headers

    @mock_dynamodb
    def test_database_error_handling(self):
        """Test database error handling"""
        self.table = self.setup_table()
        # Delete the table to simulate database error
        self.table.delete()

        add = self.add
        event = {'httpMethod': 'POST', 'body': json.dumps({'email': 'test@example.com'})}

        response = add(event, {})
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error'].startswith('Database error:')

    @mock_dynamodb
    def test_uuid_generation_uniqueness(self):
        """Test UUID generation and uniqueness"""
        self.setup_table()
        add = self.add

        # Create multiple users and verify UUIDs are unique
        emails = [f'user{i}@example.com' for i in range(5)]
        user_ids = []

        for email in emails:
            event = {'httpMethod': 'POST', 'body': json.dumps({'email': email})}
            response = add(event, {})

            assert response['statusCode'] == 201
            body = json.loads(response['body'])
            user_id = body['id']

            # Verify UUID format
            assert len(user_id) == 36
            assert user_id.count('-') == 4

            # Verify uniqueness
            assert user_id not in user_ids
            user_ids.append(user_id)

    @mock_dynamodb
    def test_email_trimming(self):
        """Test that email whitespace is properly trimmed"""
        self.setup_table()
        add = self.add

        event = {'httpMethod': 'POST', 'body': json.dumps({'email': '  test@example.com  '})}
        response = add(event, {})

        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['email'] == 'test@example.com'  # Should be trimmed


# Test fixtures for common test data
@pytest.fixture
def valid_create_user_event():
    return {'httpMethod': 'POST', 'body': json.dumps({'email': 'test@example.com'})}


@pytest.fixture
def invalid_email_event():
    return {'httpMethod': 'POST', 'body': json.dumps({'email': 'invalid-email'})}


@pytest.fixture
def missing_email_event():
    return {'httpMethod': 'POST', 'body': json.dumps({})}


@pytest.fixture
def duplicate_email_event():
    return {'httpMethod': 'POST', 'body': json.dumps({'email': 'existing@example.com'})}
