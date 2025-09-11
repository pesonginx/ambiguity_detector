import requests

# Jenkins の設定
JENKINS_URL = "https://jenkins.example.com"  # あなたのJenkins URL
JOB_PATH    = "my-job"                       # フォルダなしの場合
JOB_TOKEN   = "abc123"                       # 「Build Triggers」で設定したトークン

# パラメータ（ジョブで定義されている必要あり）
params = {
    "ENV": "dev",
    "DEPLOY_VERSION": "1.0.0"
}

# URLを組み立て
url = f"{JENKINS_URL}/job/{JOB_PATH}/buildWithParameters?token={JOB_TOKEN}"

# POSTでパラメータ送信
resp = requests.post(url, data=params)

print("status:", resp.status_code)
print("headers:", resp.headers)
print("text:", resp.text)
