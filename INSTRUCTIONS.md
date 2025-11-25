# Project Instructions

## 1. Prerequisites
- **Docker**: Ensure Docker Desktop is running.
- **Node.js**: Version 18+ installed.
- **Python**: Version 3.10+ installed.

## 2. Database Setup
Start the PostgreSQL database using Docker:
```bash
cd d:\Licenta
docker-compose up -d
```

## 3. Backend Setup
Open a terminal at `d:\Licenta\backend`:
```bash
cd d:\Licenta\backend
# Create virtual environment (if not exists)
python -m venv venv
# Activate virtual environment
venv\Scripts\activate
# Install dependencies
pip install -r requirements.txt
# Run the server
uvicorn main:app --reload
```
The backend will start at `http://localhost:8000`.

## 4. Frontend Setup
Open a **new** terminal at `d:\Licenta\frontend`:
```bash
cd d:\Licenta\frontend
# Install dependencies
npm install
# Run the development server
npm run dev
```
The frontend will be available at `http://localhost:3000`.

## 5. Data Seeding (Optional)
If you need to reset or seed data, run this from `d:\Licenta`:
```bash
cd d:\Licenta
backend\venv\Scripts\python -m backend.seeder
```

## Troubleshooting
- **Import Errors**: If you see "ModuleNotFoundError", ensure you are running `uvicorn` from the `backend` directory as shown above.
- **Database Connection**: Ensure Docker container `football_db` is running (`docker ps`).
