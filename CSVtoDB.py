import csv
from app import app, db
from models import CompanyCalendar

CSV_PATH = 'static/company_calendar.csv'  # 実際のCSVパス

with app.app_context():  # Flask アプリのコンテキスト内で操作
    with open(CSV_PATH, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 既存に同じ日付があればスキップ
            existing = CompanyCalendar.query.filter_by(date=row['date']).first()
            if existing:
                continue

            record = CompanyCalendar(
                date=row['date'],
                description=row['description'],
                type=row['type']
            )
            db.session.add(record)

        db.session.commit()
    print("CSV → DB 移行完了")
