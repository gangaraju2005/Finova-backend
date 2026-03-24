import os
import django
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from transactions.models import Category, Transaction
from users.models import UserProfile

User = get_user_model()

def run_seed():
    # 1. Create User
    email = 'karthik@example.com'
    username = 'karthikht'
    
    # Clean existing user if exists (to allow full re-seed)
    User.objects.filter(email__iexact=email).delete()
    User.objects.filter(username__iexact=username).delete()

    user = User.objects.create_user(
        email=email,
        username=username,
        password='test1234',
        first_name='Karthik',
        last_name='H T',
        is_verified=True, # Mark as verified for seeding
    )
    
    # 2. Create UserProfile
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            'monthly_savings_goal': Decimal('2000.00'),
            'phone_number': '9876543210'
        }
    )
    print(f"User {user.email} and Profile ready.")

    # 3. Create Categories matching screenshot colors/names
    now = timezone.now()

    cat_groceries = Category.objects.create(
        user=user, name="Groceries", type=Category.CategoryType.EXPENSE,
        icon_name="shopping-outline", color="#FFE2C9"
    )
    cat_transport = Category.objects.create(
        user=user, name="Transport", type=Category.CategoryType.EXPENSE,
        icon_name="car", color="#D9EDFF"
    )
    cat_subscription = Category.objects.create(
        user=user, name="Subscription", type=Category.CategoryType.EXPENSE,
        icon_name="play-box-outline", color="#F2E6FF"
    )
    cat_income = Category.objects.create(
        user=user, name="Income", type=Category.CategoryType.INCOME,
        icon_name="cash-multiple", color="#D9F9E6"
    )
    cat_shopping = Category.objects.create(
        user=user, name="Shopping", type=Category.CategoryType.EXPENSE,
        icon_name="cart-outline", color="#FFF3D6"
    )
    cat_bills = Category.objects.create(
        user=user, name="Bills", type=Category.CategoryType.EXPENSE,
        icon_name="file-document-outline", color="#E0E7FF"
    )
    cat_others = Category.objects.create(
        user=user, name="Others", type=Category.CategoryType.EXPENSE,
        icon_name="dots-horizontal", color="#E0D9CF"
    )

    # 4. Create Transactions linking exactly to totals
    # Income: $5,200
    Transaction.objects.create(
        user=user, category=cat_income, amount=Decimal('4350.00'),
        description="Salary", date=now - timedelta(days=10)
    )
    Transaction.objects.create(
        user=user, category=cat_income, amount=Decimal('850.00'),
        description="Freelance Project", date=now - timedelta(days=5)
    )

    # Shopping: 420.00
    Transaction.objects.create(
        user=user, category=cat_shopping, amount=Decimal('420.00'),
        description="Mall Shopping", date=now - timedelta(days=15)
    )
    
    # Bills: 350.00
    Transaction.objects.create(
        user=user, category=cat_bills, amount=Decimal('350.00'),
        description="Electricity Bill", date=now - timedelta(days=20)
    )

    # Others group: 180.00 (Groceries + Transport + Sub + Coffee)
    Transaction.objects.create(
        user=user, category=cat_groceries, amount=Decimal('124.50'),
        description="Whole Foods", date=now
    )
    Transaction.objects.create(
        user=user, category=cat_transport, amount=Decimal('24.00'),
        description="Uber Ride", date=now - timedelta(days=1)
    )
    Transaction.objects.create(
        user=user, category=cat_subscription, amount=Decimal('15.99'),
        description="Netflix", date=now - timedelta(days=3)
    )
    Transaction.objects.create(
        user=user, category=cat_others, amount=Decimal('15.51'),
        description="Coffee shop", date=now - timedelta(days=10)
    )

    print("Seed complete. Home dashboard amounts perfectly match design.")

if __name__ == "__main__":
    run_seed()
