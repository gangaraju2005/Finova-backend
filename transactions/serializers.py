from rest_framework import serializers
from .models import Category, Transaction, Budget, Notification

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'type', 'icon_name', 'color']

class TransactionSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True
    )

    class Meta:
        model = Transaction
        fields = ['id', 'category', 'category_id', 'amount', 'description', 'payment_method', 'date', 'created_at']

class DashboardSerializer(serializers.Serializer):
    """
    Serializer specifically for the Dashboard aggregated response.
    """
    total_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    income_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    expenses_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    saved_percentage = serializers.IntegerField(required=False, allow_null=True)
    spending_categories = serializers.ListField(
        child=serializers.DictField()
    )
    recent_transactions = TransactionSerializer(many=True)
    first_name = serializers.CharField()
    avatar_url = serializers.CharField(required=False, allow_null=True)
    unread_notifications = serializers.IntegerField(required=False, allow_null=True)

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'is_read', 'is_starred', 'created_at', 'notification_type', 'transaction_data']
