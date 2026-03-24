from django.utils.dateparse import parse_datetime
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from .models import Category

def generate_csv_export(transactions):
    output = StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow(['Date', 'Description', 'Category', 'Type', 'Amount'])
    
    for tx in transactions:
        writer.writerow([
            tx.date.strftime('%Y-%m-%d'),
            tx.description,
            tx.category.name if tx.category else 'Uncategorized',
            tx.category.get_type_display() if tx.category else 'Expense',
            tx.amount
        ])
    
    return output.getvalue()

def generate_xlsx_export(transactions):
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    
    # Headers
    headers = ['Date', 'Description', 'Category', 'Type', 'Amount']
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
            tx.amount
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

def parse_csv_import(file_file):
    import csv
    from io import TextIOWrapper
    
    # Wrap byte stream in text stream
    text_file = TextIOWrapper(file_file, encoding='utf-8')
    reader = csv.DictReader(text_file)
    
    transactions_data = []
    for row in reader:
        # Expected headers: Date, Description, Category, Type, Amount
        transactions_data.append({
            'date': row.get('Date'),
            'description': row.get('Description'),
            'category_name': row.get('Category'),
            'category_type': row.get('Type'),
            'amount': row.get('Amount')
        })
    return transactions_data

def parse_xlsx_import(file_file):
    wb = load_workbook(file_file, data_only=True)
    ws = wb.active
    
    transactions_data = []
    # Assumes first row is header
    rows = list(ws.rows)
    if not rows:
        return []
        
    headers = [cell.value for cell in rows[0]]
    
    for row in rows[1:]:
        data = {headers[i]: row[i].value for i in range(len(headers)) if i < len(headers)}
        transactions_data.append({
            'date': str(data.get('Date')) if data.get('Date') else None,
            'description': data.get('Description'),
            'category_name': data.get('Category'),
            'category_type': data.get('Type'),
            'amount': data.get('Amount')
        })
    return transactions_data
