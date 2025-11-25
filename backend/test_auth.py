import requests

def test_register():
    url = "http://localhost:8000/api/v1/auth/register"
    payload = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "password123"
    }
    try:
        response = requests.post(url, json=payload)
        print(f"Status: {response.status_code}")
        try:
            print(f"Response: {response.json()}")
        except:
            print(f"Response Text: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_register()
