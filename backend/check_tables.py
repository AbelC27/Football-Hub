from sqlalchemy import inspect
from sqlalchemy import inspect
from database import engine

def check_tables():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("Tables in database:", tables)
    
    if 'users' in tables:
        print("✅ 'users' table exists.")
        columns = [c['name'] for c in inspector.get_columns('users')]
        print("Columns:", columns)
    else:
        print("❌ 'users' table MISSING.")

if __name__ == "__main__":
    check_tables()
