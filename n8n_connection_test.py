import requests
import os

# n8n設定
N8N_URL = os.getenv("N8N_URL", "https://n8n.example.com/webhook/flow1")

# パラメータ
payload = {
    "newTag": "001",
    "oldTag": "000",
    "newTagDate": "20250117",
    "oldTagDate": "20250116",
    "gitUser": "user@gmail.com",
    "gitToken": "token",
    "workEnv": "dv0",
    "indexNameShort": "test-index"
}

# n8nのWebhookを呼び出す
print(f"Calling: {N8N_URL}")
print(f"Data: {payload}")

r = requests.post(N8N_URL, data=payload, verify=False)

print(f"Status: {r.status_code}")
print(f"Response: {r.text}")
