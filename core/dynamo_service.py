"""
core/dynamo_service.py

Providing a mock DynamoDB service for production optimizations.
Since environment doesn't have AWS credentials, this acts as a no-op fallback.
"""

class DynamoDBService:
    @staticmethod
    def get_projection(user_id, month_label):
        """Mock method for getting cached projections."""
        # return None so it always falls back to RDS for now
        return None

    @staticmethod
    def update_projection(user_id, month_label, start_date, end_date, response_data):
        """Mock method for saving projections to cache."""
        # noop
        pass
