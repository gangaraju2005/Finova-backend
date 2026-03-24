import csv
from io import StringIO, BytesIO
from datetime import datetime
from django.utils.dateparse import parse_datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from .models import Category

def generate_csv_export(transactions):
    output = StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow(['Date', 'Description', 'Category', 'Type', 'Amount', 'Payment Method'])
    
    for tx in transactions:
        writer.writerow([
            tx.date.strftime('%Y-%m-%d'),
            tx.description,
            tx.category.name if tx.category else 'Uncategorized',
            tx.category.get_type_display() if tx.category else 'Expense',
            tx.amount,
            tx.payment_method
        ])
    
    return output.getvalue().encode('utf-8')

def generate_xlsx_export(transactions):
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers
    headers = ['Date', 'Description', 'Category', 'Type', 'Amount', 'Payment Method']
    ws.append(headers)
    
    # Style headers
    header_font = Font(bold=True)
    for cell in ws[1]:
        cell.font = header_font
    
    for tx in transactions:
        ws.append([
            tx.date.strftime('%Y-%m-%d'),
            tx.description,
            tx.category.name if tx.category else 'Uncategorized',
            tx.category.get_type_display() if tx.category else 'Expense',
            tx.amount,
            tx.payment_method
        ])
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column_letter].width = adjusted_width
        
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

def generate_sample_csv():
    """Generates a sample CSV template for users to follow during import."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['date', 'amount', 'category', 'type', 'payment_method', 'description'])
    writer.writerow(['2024-03-24', '150.00', 'Groceries', 'EXPENSE', 'CREDIT_CARD', 'Weekly groceries'])
    writer.writerow(['2024-03-25', '2500.00', 'Salary', 'INCOME', 'BANK_TRANSFER', 'Monthly paycheck'])
    return output.getvalue().encode('utf-8')

def parse_csv_import(file_file):
    import csv
    from io import TextIOWrapper
    
    # Wrap byte stream in text stream
    text_file = TextIOWrapper(file_file, encoding='utf-8')
    reader = csv.DictReader(text_file)
    
    transactions_data = []
    for row in reader:
        # Normalise keys to lower for easier parsing
        data = {k.lower().strip(): v for k, v in row.items()}
        transactions_data.append({
            'date': data.get('date'),
            'description': data.get('description'),
            'category_name': data.get('category'),
            'category_type': data.get('type'),
            'amount': data.get('amount'),
            'payment_method': data.get('payment_method')
        })
    return transactions_data

def parse_xlsx_import(file_file):
    wb = load_workbook(file_file, data_only=True)
    ws = wb.active
    
    transactions_data = []
    rows = list(ws.rows)
    if not rows:
        return []
        
    headers = [str(cell.value).lower().strip() for cell in rows[0]]
    
    for row in rows[1:]:
        row_data = {headers[i]: row[i].value for i in range(len(headers)) if i < len(headers)}
        transactions_data.append({
            'date': str(row_data.get('date')) if row_data.get('date') else None,
            'description': row_data.get('description'),
            'category_name': row_data.get('category'),
            'category_type': row_data.get('type'),
            'amount': row_data.get('amount'),
            'payment_method': row_data.get('payment_method')
        })
    return transactions_data
