import boto3
import os
import logging
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)

class DynamoDBService:
    @staticmethod
    def get_client():
        aws_id = os.environ.get("AWS_ACCESS_KEY_ID")
        aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        region = os.environ.get("AWS_REGION", "us-east-1")
        table_name = os.environ.get("DYNAMO_TABLE_NAME")

        if not aws_id or not aws_secret or not table_name:
            return None, None

        try:
            dynamodb = boto3.resource(
                'dynamodb',
                aws_access_key_id=aws_id,
                aws_secret_access_key=aws_secret,
                region_name=region
            )
            return dynamodb.Table(table_name), table_name
        except Exception as e:
            logger.error(f"Failed to connect to DynamoDB: {e}")
            return None, None

    @staticmethod
    def update_projection(user_id, month_label, start_date, end_date, analytics_data):
        """
        Stores the pre-calculated analytics projection into DynamoDB.
        Partition Key: userId (String)
        Sort Key: monthLabel (String)
        """
        table, table_name = DynamoDBService.get_client()
        if not table:
            return False

        try:
            # DynamoDB requires Decimals for numbers, but analytics_data might have floats
            # We convert the whole dict recursively
            def convert_to_decimal(obj):
                if isinstance(obj, float):
                    return Decimal(str(obj))
                if isinstance(obj, dict):
                    return {k: convert_to_decimal(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [convert_to_decimal(i) for i in obj]
                return obj

            item = {
                'userId': str(user_id),
                'monthLabel': month_label,
                'startDate': str(start_date),
                'endDate': str(end_date),
                'data': convert_to_decimal(analytics_data),
                'updatedAt': str(os.environ.get("CURRENT_TIME_FALLBACK", "")) # Placeholder for timestamp
            }

            table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"Error writing to DynamoDB: {e}")
            return False

    @staticmethod
    def get_projection(user_id, month_label):
        """
        Retrieves a cached projection from DynamoDB.
        """
        table, _ = DynamoDBService.get_client()
        if not table:
            return None

        try:
            response = table.get_item(
                Key={
                    'userId': str(user_id),
                    'monthLabel': month_label
                }
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error reading from DynamoDB: {e}")
            return None
