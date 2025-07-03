import jpholiday
import csv
from datetime import datetime

class HolidayManager:
    def __init__(self, csv_path='company_calendar.csv'):
        self.company_calendar = []
        self.company_holidays = set()
        self.company_workdays = set()
        self._load_company_calendar(csv_path)

    def _load_company_calendar(self, csv_path):
            try:
                with open(csv_path, encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.company_calendar.append({
                            'date': row['date'].strip(),
                            'description': row['description'].strip(),
                            'type': row['type'].strip()
                        })
                        date_str = row['date'].strip()
                        if row['type'].strip() == 'holiday':
                            self.company_holidays.add(date_str)
                        elif row['type'].strip() == 'workday':
                            self.company_workdays.add(date_str)

            except FileNotFoundError:
                 print(f"⚠ 会社休日CSVファイルが見つかりません: {csv_path}")
            except Exception as e:
                 print(f"⚠ CSV読み込みエラー: {e}")
                   

    def is_holiday(self, date_str):
        date_obj =datetime.strptime(date_str, '%Y-%m-%d')
        mmdd = date_obj.strftime('%m-%d')
        """
        日付が土日・祝日・会社休日のいずれかなら True を返す
        """
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
        """
        会社の休日リストを返す
        """
        return sorted(self.company_calendar, key=lambda x: x['date'])
    