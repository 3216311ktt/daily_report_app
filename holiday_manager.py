import jpholiday
import csv
from datetime import datetime

class HolidayManager:
    def __init__(self, csv_path='company_calendar.csv'):
        self.csv_path = csv_path
        self.company_calendar = []
        self.company_holidays = set()
        self.company_workdays = set()
        self._load_company_calendar(csv_path)

    def _load_company_calendar(self, csv_path):
            try:
                with open(csv_path, encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    self.company_calendar.clear()
                    self.company_holidays.clear()
                    self.company_workdays.clear()
                    for row in reader:
                        row_date = {
                            'date': row['date'].strip(),
                            'description': row['description'].strip(),
                            'type': row['type'].strip()
                        }
                        self.company_calendar.append(row_date)
                        if row['type'] == 'holiday':
                            self.company_holidays.add(row_date['date'])
                        elif row_date['type'] == 'workday':
                            self.company_workdays.add(row_date['date'])
            except FileNotFoundError:
                print(f"⚠ CSVファイルが見つかりません: {csv_path}")
            except Exception as e:
                print(f"⚠ CSV読み込みエラー: {e}")

    
    def save_calendar(self, csv_path='company_calendar.csv'):
        """
        会社の休日リストをCSVに保存
        """
        try:
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['date', 'description', 'type'])
                writer.writeheader()
                for row in self.company_calendar:
                    writer.writerow(row)
            print(f"✅ 会社休日リストを {csv_path} に保存しました。")
        except Exception as e:
            print(f"⚠ CSV保存エラー: {e}")
                   

    def is_holiday(self, date_str):
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
             return False
        
        mmdd = date_obj.strftime('%m-%d')
        
        if date_str in self.company_workdays:
            return False
        
        return (
            jpholiday.is_holiday(date_obj) or
            date_obj.weekday() >= 5 or
            mmdd in self.company_holidays
            )

    def is_company_holidays(self, date_str):
        """
        会社独自の休日のみ判定したい場合
        """
        return date_str in self.company_holidays
    
    @property
    def calendar_list(self):
        # 年付きと年なしを分ける
        year_items = []
        no_year_items = []

        for item in self.company_calendar:
            if len(item['date'].split('-')) == 3:  # 年月日形式
                year_items.append(item)
            else:
                no_year_items.append(item)

        year_items = sorted(year_items, key=lambda x: x['date'])
        no_year_items = sorted(no_year_items, key=lambda x:x['date'])

        # 年付き→ 年なしの順に返す  
        return year_items + no_year_items
    