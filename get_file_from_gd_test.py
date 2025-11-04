import argparse
import os
import re
from typing import Optional

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


def extract_file_id_from_url(url: str) -> Optional[str]:
    """
    代表的なGoogle Drive共有URLからfileIdを抽出する簡易関数。
    対応例:
      - https://drive.google.com/file/d/<FILE_ID>/view?...
      - https://drive.google.com/open?id=<FILE_ID>
      - https://drive.google.com/uc?id=<FILE_ID>&export=download
    """
    patterns = [
        r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)",
        r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)",
        r"drive\.google\.com/uc\?id=([a-zA-Z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def auth_with_service_account(sa_json_path: str) -> GoogleDrive:
    settings = {
        "client_config_backend": "service",
        "service_config": {
            "client_json_file_path": sa_json_path,
        },
    }
    gauth = GoogleAuth(settings=settings)
    gauth.ServiceAuth()
    return GoogleDrive(gauth)


def auth_with_oauth(client_secrets: Optional[str], creds_file: str) -> GoogleDrive:
    # PyDrive2はsettingsでclient_secretsやcredentials保存先を指定できる
    settings = {
        "client_config_backend": "file",
        "client_config_file": client_secrets or "client_secrets.json",
        "save_credentials": True,
        "save_credentials_backend": "file",
        "save_credentials_file": creds_file,
        "get_refresh_token": True,
        "oauth_scope": [
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    }
    gauth = GoogleAuth(settings=settings)
    # 既存トークンがあれば読み込み、無ければブラウザで認証
    try:
        gauth.LoadCredentialsFile(creds_file)
    except Exception:
        pass
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
        gauth.SaveCredentialsFile(creds_file)
    elif gauth.access_token_expired:
        gauth.Refresh()
        gauth.SaveCredentialsFile(creds_file)
    else:
        gauth.Authorize()
    return GoogleDrive(gauth)


def download_with_pydrive(drive: GoogleDrive, file_id: str, destination_path: str) -> None:
    os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
    gfile = drive.CreateFile({"id": file_id})
    gfile.GetContentFile(destination_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PyDrive2 を使って Google Drive からファイルを取得する簡易テストツール",
    )
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--id", dest="file_id", help="Google DriveのファイルID")
    id_group.add_argument("--url", dest="share_url", help="Google Driveの共有URL")

    auth_group = parser.add_mutually_exclusive_group(required=False)
    auth_group.add_argument("--sa-json", dest="sa_json", help="サービスアカウントJSONのパス")
    auth_group.add_argument("--client-secrets", dest="client_secrets", help="OAuth用 client_secrets.json のパス")

    parser.add_argument(
        "--creds",
        dest="creds_file",
        default="pydrive2_creds.json",
        help="OAuth資格情報の保存先 (既定: pydrive2_creds.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="保存先パス (未指定時は <FILE_ID>.bin)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.file_id:
        file_id = args.file_id
    else:
        extracted = extract_file_id_from_url(args.share_url)
        if not extracted:
            raise SystemExit("共有URLからfileIdを抽出できませんでした。--idで指定してください。")
        file_id = extracted

    output_path = args.output or f"{file_id}.bin"

    if args.sa_json:
        drive = auth_with_service_account(args.sa_json)
    else:
        drive = auth_with_oauth(args.client_secrets, args.creds_file)

    print(f"Downloading file_id={file_id} -> {output_path} ...")
    download_with_pydrive(drive, file_id, output_path)
    print("Done.")


if __name__ == "__main__":
    main()


