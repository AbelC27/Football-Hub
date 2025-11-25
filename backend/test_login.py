import requests

def test_login():
    url = "http://localhost:8000/api/v1/auth/login"
    payload = {
        "username": "testuser",
        "password": "password123"
    }
    try:
        response = requests.post(url, data=payload) # OAuth2 uses form data, not JSON
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_login()
