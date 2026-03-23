"""
transactions/views.py

All views for the transactions app:
  - DashboardView              GET  /api/transactions/dashboard/
  - AnalyticsView              GET  /api/transactions/analytics/
  - CategoryListView           GET  /api/transactions/categories/
  - TransactionListCreateView  GET/POST /api/transactions/
"""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Sum, Q
from django.db import models
from rest_framework import permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse

from .models import Category, Transaction, Budget, Notification
from .serializers import DashboardSerializer, CategorySerializer, TransactionSerializer
from .export_utils import (
    generate_csv_export, generate_xlsx_export,
    parse_csv_import, parse_xlsx_import,
    generate_sample_csv,
)
from rest_framework.parsers import MultiPartParser, FormParser
from core.dynamo_service import DynamoDBService


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class DashboardView(APIView):
    """
    GET /api/transactions/dashboard/

    Returns aggregated totals, savings percentage, spending breakdown,
    and the 4 most recent transactions for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        transactions = Transaction.objects.filter(user=user)

        # Totals
        income_total = transactions.filter(
            category__type=Category.CategoryType.INCOME
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        expenses_total = transactions.filter(
            category__type=Category.CategoryType.EXPENSE
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        total_balance = income_total - expenses_total

        # Saved percentage: e.g. "SAVED 35%"
        saved_percentage = None
        if income_total > 0:
            saved_percentage = int(((income_total - expenses_total) / income_total) * 100)
            saved_percentage = max(saved_percentage, 0)

        # Spending breakdown grouped by expense category (top 2 + "Others")
        expenses_qs = transactions.filter(category__type=Category.CategoryType.EXPENSE)
        category_totals = defaultdict(Decimal)
        for exp in expenses_qs:
            category_totals[exp.category] += exp.amount

        sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

        spending_categories = [
            {'name': cat.name, 'color': cat.color, 'amount': float(amt)}
            for cat, amt in sorted_categories[:2]
        ]
        if len(sorted_categories) > 2:
            others_amount = sum(amt for _, amt in sorted_categories[2:])
            spending_categories.append({'name': 'Others', 'color': '#C9C4BB', 'amount': float(others_amount)})

        # 4 most recent transactions
        recent_transactions = transactions.order_by('-date')[:4]

        data = {
            'first_name':          user.first_name or user.email.split('@')[0],
            'avatar_url':          user.profile.avatar_url if hasattr(user, 'profile') else None,
            'total_balance':       total_balance,
            'income_total':        income_total,
            'expenses_total':      expenses_total,
            'saved_percentage':    saved_percentage,
            'spending_categories': spending_categories,
            'recent_transactions': recent_transactions,
            'unread_notifications': Notification.objects.filter(user=user, is_read=False).count(),
        }

        serializer = DashboardSerializer(data)
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsView(APIView):
    """
    GET /api/transactions/analytics/

    Returns monthly spend vs budget, weekly breakdown (W1–W4),
    and top 5 expense categories with transaction counts and percentages.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user  = request.user
        today = date.today()
        timeframe = request.query_params.get('timeframe', 'month')
        category_ids = request.query_params.get('category_id')
        payment_methods = request.query_params.get('payment_method')

        from datetime import timedelta
        import calendar

        # Timeframe date ranges
        if timeframe == 'year':
            try:
                # Handle leap year replacement constraints gracefully
                start_date = today.replace(year=today.year - 1)
            except ValueError:
                start_date = today.replace(year=today.year - 1, day=28)
            end_date = today
            month_label = f"{start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')}"
        elif timeframe == 'quarter':
            quarter = (today.month - 1) // 3 + 1
            start_month = 3 * (quarter - 1) + 1
            start_date = today.replace(month=start_month, day=1)
            end_month = start_month + 2
            _, last_day = calendar.monthrange(today.year, end_month)
            end_date = today.replace(month=end_month, day=last_day)
            month_label = f"Q{quarter} {today.year}"
        elif timeframe == 'week':
            start_date = today - timedelta(days=today.weekday()) # Monday
            end_date = start_date + timedelta(days=6)            # Sunday
            month_label = "This Week"
        elif timeframe == 'last_3_months':
            start_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=1)
            start_date = start_date.replace(day=1) # start of 2 months ago (total 3 months including current)
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = today.replace(day=last_day)
            month_label = "Last 3 Months"
        else:
            # Default to current month
            start_date = today.replace(day=1)
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = today.replace(day=last_day)
            month_label = today.strftime('%B %Y')

        # --- DYNAMODB PROJECTION CHECK (Production Optimization) ---
        # Skip if filters are applied to ensure RDS provides fresh filtered data
        has_filters = any([category_ids, payment_methods])
        if not has_filters:
            cached_data = DynamoDBService.get_projection(user.id, month_label)
            if cached_data:
                # Return the cached data from DynamoDB (convert Decimals back to floats/ints for JSON)
                def convert_from_decimal(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    if isinstance(obj, dict):
                        return {k: convert_from_decimal(v) for k, v in obj.items()}
                    if isinstance(obj, list):
                        return [convert_from_decimal(i) for i in obj]
                    return obj
                return Response(convert_from_decimal(cached_data['data']))

        # --- RDS CALCULATION (Local Fallback or Cache Miss) ---
        month_txns = Transaction.objects.filter(
            user=user,
            date__date__gte=start_date,
            date__date__lte=end_date,
        )

        if category_ids:
            cat_list = [c.strip() for c in category_ids.split(',') if c.strip()]
            if cat_list:
                month_txns = month_txns.filter(category_id__in=cat_list)
        if payment_methods:
            pm_list = [p.strip() for p in payment_methods.split(',') if p.strip()]
            if pm_list:
                month_txns = month_txns.filter(payment_method__in=pm_list)

        # Spent total (expenses only)
        expense_qs = month_txns.filter(category__type=Category.CategoryType.EXPENSE)
        spent_total = expense_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Budget total — Aggregate across all months in timeframe
        budget_qs = Budget.objects.filter(
            user=user,
            month__gte=start_date.replace(day=1),
            month__lte=end_date
        )
        if category_ids:
            cat_list = [c.strip() for c in category_ids.split(',') if c.strip()]
            if cat_list:
                budget_qs = budget_qs.filter(category_id__in=cat_list)
            
        budget_total = budget_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        budget_on_track = bool(spent_total <= budget_total) if budget_total > 0 else None

        # Chart breakdown
        if timeframe == 'year':
            months_map = {}
            active_months = []
            curr = start_date.replace(day=1)
            end_month = end_date.replace(day=1)
            
            # Map up to the current month
            while curr <= end_month:
                label = curr.strftime('%b %y')
                if label not in months_map:
                    months_map[label] = {'expense': Decimal('0'), 'income': Decimal('0')}
                    active_months.append(label)
                _, last_day = calendar.monthrange(curr.year, curr.month)
                curr = curr + timedelta(days=last_day)
                
            for txn in month_txns:
                txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                label = txn_date.strftime('%b %y')
                if label in months_map and txn.category:
                    if txn.category.type == Category.CategoryType.EXPENSE:
                        months_map[label]['expense'] += txn.amount
                    elif txn.category.type == Category.CategoryType.INCOME:
                        months_map[label]['income'] += txn.amount
            weekly_data = [{'label': k, 'amount': float(months_map[k]['expense']), 'income_amount': float(months_map[k]['income'])} for k in active_months]

        elif timeframe == 'quarter':
            qr_months = [calendar.month_abbr[i] for i in range(start_month, start_month + 3)]
            month_map = {m: {'expense': Decimal('0'), 'income': Decimal('0')} for m in qr_months}
            for txn in month_txns:
                txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                label = txn_date.strftime('%b')
                if label in month_map and txn.category:
                    if txn.category.type == Category.CategoryType.EXPENSE:
                        month_map[label]['expense'] += txn.amount
                    elif txn.category.type == Category.CategoryType.INCOME:
                        month_map[label]['income'] += txn.amount
            weekly_data = [{'label': k, 'amount': float(v['expense']), 'income_amount': float(v['income'])} for k, v in month_map.items()]

        elif timeframe == 'last_3_months':
            month_map = {m: {'expense': Decimal('0'), 'income': Decimal('0')} for m in calendar.month_abbr[1:]} # init all
            active_months = []
            for i in range(3):
                m_date = start_date + timedelta(days=i*30 + 15) # approx mid of month
                label = m_date.strftime('%b')
                if label not in active_months:
                    active_months.append(label)
            
            for txn in month_txns:
                txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                label = txn_date.strftime('%b')
                if label in month_map and txn.category:
                    if txn.category.type == Category.CategoryType.EXPENSE:
                        month_map[label]['expense'] += txn.amount
                    elif txn.category.type == Category.CategoryType.INCOME:
                        month_map[label]['income'] += txn.amount
            weekly_data = [{'label': k, 'amount': float(month_map[k]['expense']), 'income_amount': float(month_map[k]['income'])} for k in active_months]

        elif timeframe == 'week':
            days_map = {}
            active_days = []
            for i in range(7):
                d = start_date + timedelta(days=i)
                label = d.strftime('%a') # e.g. Mon, Tue
                days_map[label] = {'expense': Decimal('0'), 'income': Decimal('0')}
                active_days.append(label)
                
            for txn in month_txns:
                txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                label = txn_date.strftime('%a')
                if label in days_map and txn.category:
                    if txn.category.type == Category.CategoryType.EXPENSE:
                        days_map[label]['expense'] += txn.amount
                    elif txn.category.type == Category.CategoryType.INCOME:
                        days_map[label]['income'] += txn.amount
            weekly_data = [{'label': k, 'amount': float(days_map[k]['expense']), 'income_amount': float(days_map[k]['income'])} for k in active_days]

        elif timeframe == 'custom':
            total_days = (end_date - start_date).days + 1
            if total_days <= 31:
                days_map = {}
                active_days = []
                for i in range(total_days):
                    d = start_date + timedelta(days=i)
                    label = d.strftime('%b %d')
                    if d.year != today.year:
                        label = d.strftime('%b %d %Y')
                    days_map[label] = {'expense': Decimal('0'), 'income': Decimal('0')}
                    active_days.append(label)
                for txn in month_txns:
                    txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                    label = txn_date.strftime('%b %d')
                    if txn_date.year != today.year:
                        label = txn_date.strftime('%b %d %Y')
                    if label in days_map and txn.category:
                        if txn.category.type == Category.CategoryType.EXPENSE:
                            days_map[label]['expense'] += txn.amount
                        elif txn.category.type == Category.CategoryType.INCOME:
                            days_map[label]['income'] += txn.amount
                weekly_data = [{'label': k, 'amount': float(days_map[k]['expense']), 'income_amount': float(days_map[k]['income'])} for k in active_days]
            elif total_days <= 180:
                weeks_map = {}
                active_weeks = []
                curr = start_date
                while curr <= end_date:
                    next_curr = min(curr + timedelta(days=6), end_date)
                    label = f"{curr.strftime('%b %d')} - {next_curr.strftime('%b %d')}"
                    if curr.year != next_curr.year or curr.year != today.year:
                        label = f"{curr.strftime('%b %d %y')} - {next_curr.strftime('%b %d %y')}"
                    weeks_map[label] = {'expense': Decimal('0'), 'income': Decimal('0')}
                    active_weeks.append({'start': curr, 'end': next_curr, 'label': label})
                    curr = next_curr + timedelta(days=1)
                for txn in month_txns:
                    txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                    for aw in active_weeks:
                        if aw['start'] <= txn_date <= aw['end'] and txn.category:
                            if txn.category.type == Category.CategoryType.EXPENSE:
                                weeks_map[aw['label']]['expense'] += txn.amount
                            elif txn.category.type == Category.CategoryType.INCOME:
                                weeks_map[aw['label']]['income'] += txn.amount
                            break
                weekly_data = [{'label': aw['label'], 'amount': float(weeks_map[aw['label']]['expense']), 'income_amount': float(weeks_map[aw['label']]['income'])} for aw in active_weeks]
            else:
                months_map = {}
                active_months = []
                curr = start_date.replace(day=1)
                while curr <= end_date:
                    label = curr.strftime('%b %Y')
                    if label not in months_map:
                        months_map[label] = {'expense': Decimal('0'), 'income': Decimal('0')}
                        active_months.append({'month': curr.month, 'year': curr.year, 'label': label})
                    _, last_day = calendar.monthrange(curr.year, curr.month)
                    curr = curr + timedelta(days=last_day)
                for txn in month_txns:
                    txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                    label = txn_date.strftime('%b %Y')
                    if label in months_map and txn.category:
                        if txn.category.type == Category.CategoryType.EXPENSE:
                            months_map[label]['expense'] += txn.amount
                        elif txn.category.type == Category.CategoryType.INCOME:
                            months_map[label]['income'] += txn.amount
                weekly_data = [{'label': am['label'], 'amount': float(months_map[am['label']]['expense']), 'income_amount': float(months_map[am['label']]['income'])} for am in active_months]

        else: # month
            weekly = {'W1': {'expense': Decimal('0'), 'income': Decimal('0')}, 
                      'W2': {'expense': Decimal('0'), 'income': Decimal('0')}, 
                      'W3': {'expense': Decimal('0'), 'income': Decimal('0')}, 
                      'W4': {'expense': Decimal('0'), 'income': Decimal('0')}}
            for txn in month_txns:
                txn_date = txn.date if isinstance(txn.date, date) else txn.date.date()
                day = txn_date.day
                w_key = 'W1'
                if day <= 7: w_key = 'W1'
                elif day <= 14: w_key = 'W2'
                elif day <= 21: w_key = 'W3'
                else: w_key = 'W4'
                
                if txn.category:
                    if txn.category.type == Category.CategoryType.EXPENSE:
                        weekly[w_key]['expense'] += txn.amount
                    elif txn.category.type == Category.CategoryType.INCOME:
                        weekly[w_key]['income'] += txn.amount
                
            weekly_data = [{'label': k, 'amount': float(v['expense']), 'income_amount': float(v['income'])} for k, v in weekly.items()]

        # Top 5 expense categories
        cat_map = defaultdict(lambda: {'amount': Decimal('0'), 'count': 0, 'obj': None})
        for txn in expense_qs.select_related('category'):
            if txn.category is None:
                continue
            entry = cat_map[txn.category_id]
            entry['amount'] += txn.amount
            entry['count']  += 1
            entry['obj']     = txn.category

        sorted_cats = sorted(cat_map.values(), key=lambda x: x['amount'], reverse=True)

        top_categories = []
        for item in sorted_cats[:5]:
            cat = item['obj']
            pct = int(item['amount'] / spent_total * 100) if spent_total > 0 else 0
            
            cat_budget_qs = budget_qs.filter(category_id=cat.id)
            cat_budget = cat_budget_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            remaining = cat_budget - item['amount']
            
            top_categories.append({
                'id':         cat.id,
                'name':       cat.name,
                'icon_name':  cat.icon_name,
                'color':      cat.color,
                'amount':     float(item['amount']),
                'count':      item['count'],
                'percentage': pct,
                'budget_amount': float(cat_budget),
                'remaining':  float(remaining),
            })

        response_data = {
            'month_label':    month_label,
            'spent_total':    float(spent_total),
            'budget_total':   float(budget_total),
            'budget_on_track': budget_on_track,
            'weekly_data':    weekly_data,
            'top_categories': top_categories,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
        }

        # --- PUSH TO DYNAMODB (Background Sync) ---
        if not has_filters:
            DynamoDBService.update_projection(user.id, month_label, start_date, end_date, response_data)

        return Response(response_data)


# ─────────────────────────────────────────────────────────────────────────────
# Categories
# ─────────────────────────────────────────────────────────────────────────────

class CategoryListView(generics.ListAPIView):
    """
    GET /api/transactions/categories/

    Returns all global default categories plus any user-created ones.
    Auto-seeds global defaults on first call if the table is empty.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CategorySerializer

    def get_queryset(self):
        if not Category.objects.filter(user=None).exists():
            defaults = [
                {'name': 'Food',      'type': Category.CategoryType.EXPENSE, 'icon_name': 'silverware-fork-knife', 'color': '#FFE2C9'},
                {'name': 'Transport', 'type': Category.CategoryType.EXPENSE, 'icon_name': 'car-hatchback',         'color': '#D9EDFF'},
                {'name': 'Shopping',  'type': Category.CategoryType.EXPENSE, 'icon_name': 'shopping-outline',      'color': '#F2E6FF'},
                {'name': 'Health',    'type': Category.CategoryType.EXPENSE, 'icon_name': 'medical-bag',           'color': '#D9F9E6'},
                {'name': 'Bills',     'type': Category.CategoryType.EXPENSE, 'icon_name': 'receipt',               'color': '#2C2C2C'},
                {'name': 'Fun',       'type': Category.CategoryType.EXPENSE, 'icon_name': 'movie-open-outline',    'color': '#FFDDF4'},
                {'name': 'Education', 'type': Category.CategoryType.EXPENSE, 'icon_name': 'school-outline',        'color': '#EAEAEA'},
                {'name': 'Salary',    'type': Category.CategoryType.INCOME,  'icon_name': 'cash-multiple',         'color': '#D9F9E6'},
                {'name': 'Freelance', 'type': Category.CategoryType.INCOME,  'icon_name': 'laptop-account',        'color': '#C4A44A'},
            ]
            for cat in defaults:
                Category.objects.create(user=None, **cat)

        return Category.objects.filter(user=None) | Category.objects.filter(user=self.request.user)


# ─────────────────────────────────────────────────────────────────────────────
# Transactions
# ─────────────────────────────────────────────────────────────────────────────

class TransactionListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/transactions/  — list the user's transactions (newest first)
    POST /api/transactions/  — create a new transaction
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = TransactionSerializer

    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user).order_by('-date')
        category_ids = self.request.query_params.get('category_id')
        payment_methods = self.request.query_params.get('payment_method')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        if category_ids:
            cat_list = [c.strip() for c in category_ids.split(',') if c.strip()]
            if cat_list:
                queryset = queryset.filter(category_id__in=cat_list)
                
        if payment_methods:
            pm_list = [p.strip() for p in payment_methods.split(',') if p.strip()]
            if pm_list:
                queryset = queryset.filter(payment_method__in=pm_list)
        if start_date:
            queryset = queryset.filter(date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__date__lte=end_date)
            
        return queryset

    def perform_create(self, serializer):
        txn = serializer.save(user=self.request.user)
        Notification.objects.create(
            user=self.request.user,
            title="Transaction Added",
            message=f"Added '{txn.description}' for ${txn.amount}.",
            notification_type='ADDED',
            transaction_data=TransactionSerializer(txn).data
        )
        self.check_budget(txn)

    def check_budget(self, txn):
        if txn.category and txn.category.type == Category.CategoryType.EXPENSE:
            from datetime import date
            month_start = date.today().replace(day=1)
            budget = Budget.objects.filter(user=txn.user, category=txn.category, month=month_start).first()
            if budget:
                month_txns = Transaction.objects.filter(
                    user=txn.user, category=txn.category, 
                    date__year=date.today().year, date__month=date.today().month
                ).aggregate(total=Sum('amount'))['total'] or 0
                if month_txns > budget.amount:
                    Notification.objects.create(
                        user=txn.user,
                        title="Budget Exceeded!",
                        message=f"You exceeded your {txn.category.name} budget. Total spent: ${month_txns} / Limit: ${budget.amount}.",
                        notification_type='BUDGET',
                        transaction_data=TransactionSerializer(txn).data
                    )


class TransactionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/transactions/<id>/ — get transaction details
    PUT    /api/transactions/<id>/ — update transaction completely
    PATCH  /api/transactions/<id>/ — update transaction partially
    DELETE /api/transactions/<id>/ — delete transaction
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        txn = serializer.save()
        Notification.objects.create(
            user=self.request.user,
            title="Transaction Updated",
            message=f"Updated '{txn.description}' to ${txn.amount}.",
            notification_type='UPDATED',
            transaction_data=TransactionSerializer(txn).data
        )
        # Check budget on update
        TransactionListCreateView().check_budget(txn)

    def perform_destroy(self, instance):
        txn_data = TransactionSerializer(instance).data
        Notification.objects.create(
            user=self.request.user,
            title="Transaction Deleted",
            message=f"Deleted '{instance.description}' of ${instance.amount}.",
            notification_type='DELETED',
            transaction_data=txn_data
        )
        instance.delete()


# ─────────────────────────────────────────────────────────────────────────────
# Budgets
# ─────────────────────────────────────────────────────────────────────────────

class BudgetView(APIView):
    """
    GET /api/transactions/budgets/ — returns all expense categories and their current month's budget
    PUT /api/transactions/budgets/ — replaces current month's budgets with provided array
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        today = date.today()
        month_start = today.replace(day=1)

        from django.db import models
        categories = Category.objects.filter(type=Category.CategoryType.EXPENSE).filter(
            models.Q(user=None) | models.Q(user=user)
        ).order_by('id')
        
        import calendar as cal_mod
        budgets = Budget.objects.filter(user=user, month=month_start)
        budget_map = {b.category_id: b.amount for b in budgets}

        # Compute spent this month per category
        _, last_day = cal_mod.monthrange(today.year, today.month)
        month_end = today.replace(day=last_day)
        txns = Transaction.objects.filter(
            user=user,
            date__date__gte=month_start,
            date__date__lte=month_end,
            category__type=Category.CategoryType.EXPENSE,
        ).values('category_id').annotate(total=Sum('amount'))
        spent_map = {row['category_id']: float(row['total']) for row in txns}

        data = []
        for cat in categories:
            budget_amt = float(budget_map[cat.id]) if cat.id in budget_map else None
            spent_amt  = spent_map.get(cat.id, 0.0)
            remaining  = round(budget_amt - spent_amt, 2) if budget_amt is not None else None
            data.append({
                'category_id': cat.id,
                'name':        cat.name,
                'icon_name':   cat.icon_name,
                'color':       cat.color,
                'amount':      budget_amt,
                'spent':       spent_amt,
                'remaining':   remaining,
            })
        
        return Response(data)

    def put(self, request):
        user = request.user
        today = date.today()
        month_start = today.replace(day=1)

        budget_data = request.data.get('budgets', [])

        # Clear existing for the month
        Budget.objects.filter(user=user, month=month_start).delete()

        # Insert new
        new_budgets = []
        for item in budget_data:
            cat_id = item.get('category_id')
            amount = item.get('amount')
            if cat_id and amount is not None:
                try:
                    val = Decimal(str(amount))
                    if val > 0:
                        new_budgets.append(
                            Budget(user=user, category_id=cat_id, amount=val, month=month_start)
                        )
                except Exception:
                    pass
        
        if new_budgets:
            Budget.objects.bulk_create(new_budgets)
            desc = ", ".join([f"{b.category.name} (${b.amount})" for b in new_budgets])
            Notification.objects.create(
                user=user,
                title="Budgets Updated",
                message="Your monthly budgets were updated.",
                notification_type="BUDGET"
            )

        return Response({'status': 'success'})

# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────
from .serializers import NotificationSerializer

class NotificationListView(generics.ListAPIView):
    """
    GET /api/transactions/notifications/ — returns user's notifications
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

class NotificationReadView(APIView):
    """
    POST /api/transactions/notifications/read/ — marks all as read
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'success'})

class NotificationStarView(APIView):
    """
    POST /api/transactions/notifications/<id>/star/ — toggle star on a notification
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, user=request.user)
            notif.is_starred = not notif.is_starred
            notif.save()
            return Response({'is_starred': notif.is_starred})
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

class NotificationClearView(APIView):
    """
    DELETE /api/transactions/notifications/clear/ — delete all non-starred notifications
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(user=request.user, is_starred=False).delete()
        return Response({'deleted': deleted_count})

class NotificationBulkDeleteView(APIView):
    """
    POST /api/transactions/notifications/bulk-delete/ — delete specific notifications by IDs
    Body: { "ids": [1, 2, 3] }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'error': 'No IDs provided'}, status=400)
        deleted_count, _ = Notification.objects.filter(user=request.user, pk__in=ids).delete()
        return Response({'deleted': deleted_count})


# ─────────────────────────────────────────────────────────────────────────────
# Data Export, Import & Cleanup
# ─────────────────────────────────────────────────────────────────────────────

class ExportTransactionsView(APIView):
    """
    GET /api/transactions/export/?format=csv|xlsx
    GET /api/transactions/export/?format=sample  — download a sample CSV template
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        export_format = request.query_params.get('format', 'csv').lower()

        # ── Sample template ──────────────────────────────────────────────────
        if export_format == 'sample':
            content = generate_sample_csv()
            response = HttpResponse(content, content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="finovo_sample_template.csv"'
            return response

        transactions = Transaction.objects.filter(user=request.user).select_related('category').order_by('-date')

        if export_format == 'csv':
            content = generate_csv_export(transactions)
            response = HttpResponse(content, content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="finovo_transactions_{date.today()}.csv"'
            return response

        elif export_format == 'xlsx':
            content = generate_xlsx_export(transactions)
            response = HttpResponse(
                content,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="finovo_transactions_{date.today()}.xlsx"'
            return response

        return Response({'error': 'Unsupported format. Use ?format=csv or ?format=xlsx'}, status=400)


class CleanupDataView(APIView):
    """
    DELETE /api/transactions/cleanup/ — delete all transactions for user
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        deleted_tx, _ = Transaction.objects.filter(user=request.user).delete()
        return Response({
            'message': 'Data cleared successfully',
            'deleted_transactions': deleted_tx
        })


class ImportTransactionsView(APIView):
    """
    POST /api/transactions/import/
    Body: multipart/form-data with 'file' field (.csv or .xlsx)

    Returns:
        {
          "success_count": N,
          "failed_count": M,
          "failed_rows": [ { "row": 3, "reason": "..." }, ... ]
        }
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    # File size limit: 5 MB
    MAX_FILE_SIZE = 5 * 1024 * 1024

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=400)

        # ── File size check ─────────────────────────────────────────────────
        if file_obj.size > self.MAX_FILE_SIZE:
            return Response({'error': 'File too large. Maximum allowed size is 5 MB.'}, status=400)

        filename = file_obj.name.lower()
        try:
            if filename.endswith('.csv'):
                data_list = parse_csv_import(file_obj)
            elif filename.endswith('.xlsx'):
                data_list = parse_xlsx_import(file_obj)
            else:
                return Response(
                    {'error': 'Unsupported file format. Please upload a .csv or .xlsx file.'},
                    status=400
                )
        except Exception as e:
            return Response({'error': f'Could not read file: {str(e)}'}, status=400)

        if not data_list:
            return Response({'error': 'The file is empty or has no data rows.'}, status=400)

        # ── Category cache: avoid repeated DB hits ─────────────────────────
        # Pre-load all categories available to this user
        existing_categories = {
            (cat.name.lower(), cat.type): cat
            for cat in Category.objects.filter(
                Q(user=request.user) | Q(user__isnull=True)
            )
        }
        new_categories = {}

        to_create = []
        failed_rows = []

        for row in data_list:
            row_num = row.get('row_num', '?')

            # ── Collect validation errors from normalisation ──
            errors = row.get('errors', [])

            if row.get('amount') is None:
                # amount parsing already added an error; skip
                failed_rows.append({'row': row_num, 'reason': '; '.join(errors)})
                continue

            if errors:
                # Non-fatal validation issues (e.g. bad date defaulted) — still import
                # but only skip if description is missing
                if not row.get('description'):
                    failed_rows.append({'row': row_num, 'reason': '; '.join(errors)})
                    continue

            # ── Category resolution ──────────────────────────────────────────
            cat_name = row['category_name']
            cat_type = row['category_type']   # 'INCOME' or 'EXPENSE'
            cache_key = (cat_name.lower(), cat_type)

            if cache_key in existing_categories:
                category = existing_categories[cache_key]
            elif cache_key in new_categories:
                category = new_categories[cache_key]
            else:
                # Create a user-specific category on the fly
                category = Category(
                    user=request.user,
                    name=cat_name,
                    type=cat_type,
                    icon_name='help-circle-outline',
                    color='#94A3B8'
                )
                category.save()   # save individually so FK works in Transaction
                new_categories[cache_key] = category
                existing_categories[cache_key] = category

            # ── Build Transaction object ─────────────────────────────────────
            to_create.append(Transaction(
                user=request.user,
                category=category,
                amount=Decimal(str(row['amount'])),
                description=row['description'],
                payment_method=row['payment_method'],
                date=row['date'],
            ))

        # ── Bulk insert in chunks of 500 ────────────────────────────────────
        CHUNK_SIZE = 500
        success_count = 0
        for i in range(0, len(to_create), CHUNK_SIZE):
            chunk = to_create[i:i + CHUNK_SIZE]
            Transaction.objects.bulk_create(chunk)
            success_count += len(chunk)

        return Response({
            'message': f'Import complete. {success_count} transactions imported.',
            'success_count': success_count,
            'failed_count': len(failed_rows),
            'failed_rows': failed_rows,
        })
