#!/bin/bash

# 多重起動防止のためregister_index_sh.lockファイルがある場合は処理スキップする
LOCK_FILE="./register_index_sh.lock"
# 多重起動チェック処理
if [ -e "${LOCK_FILE}" ]; then
    echo "別のプロセスが実行中です。処理をスキップします。"
    exit 0
else
    # ロックファイルを作成
    touch "${LOCK_FILE}"
fi

# スクリプト終了時にロックファイルを削除する処理をTrapする
trap 'rm -f "${LOCK_FILE}"; exit 0' INT TERM EXIT

# 環境変数設定
## ARTIFACTORY接続情報
ARTIFACTORY_USERNAME=""
ARTIFACTORY_PASSWORD=""
ARTIFACTORY_URL=""

## 配信サーバ上で管理しているインデクス作成済みタグ一覧のファイル
CREATED_INDEX_TAG_FILE="./created_index_tag_list.txt"
# ※ スクリプト内で使用するファイルの場所は考えておいた方がいいかも

## 当スクリプトで使用するファイル
TEMP_SERVER_TAG_FILE="/tmp/artifactory_deploy_tags.txt"
TEMP_SORTED_SERVER_TAG_FILE="/tmp/sorted_remote_cca_deploy_tags.txt"
TEMP_MISSING_TAGS_FILE="/tmp/missing_tags.txt"
TEMP_N8N_RESPONSE="/tmp/n8n_response.txt"

## n8n動作アカウント情報
GIT_USER=""
GIT_PASS=""  # ここはJenkinsに渡すGIT_TOKENに同じ

## n8n実行URL
N8N_FLOW_URL1="" # ここに実行するURLを記載してください！
N8N_FLOW_URL2=""


## 実行環境リスト
WORK_ENVS=("dv0" "dv1" "itb" "uat")
INDEX_NAME_SHORT=""

## ログ出力ディレクトリ
LOG_DIR="./log"
mkdir -p "${LOG_DIR}"
# ※ ログファイル名は環境・日付ごとにループ内で決める


# ArtifactoryからTAGファイルを取得
echo "ArtifactoryからTAGファイルを取得します..."
curl -s -u ${ARTIFACTORY_USERNAME}:${ARTIFACTORY_PASSWORD} -O ${TEMP_SERVER_TAG_FILE} ${ARTIFACTORY_URL}

# 取得エラーチェック
if [ $? -ne 0 ]; then
    echo "ArtifactoryからTAGファイルの取得に失敗しました。スクリプトを終了します。"
    exit 1
fi

# ローカルのTAGファイルが存在しない場合、新規作成
if [ ! -e ${CREATED_INDEX_TAG_FILE} ]; then
    echo "ローカルのTAGファイルが存在しないため、新規作成します..."
    cp ${TEMP_SERVER_TAG_FILE} ${CREATED_INDEX_TAG_FILE}
    exit 0
fi

# サーバのTAGファイルをソート
sort ${TEMP_SERVER_TAG_FILE} -o ${TEMP_SORTED_SERVER_TAG_FILE}

# 差分を抽出
echo "ローカルファイルとArtifactoryファイルを比較し、不足しているTAGを取得します..."
MISSING_TAGS=""
while IFS= read -r server_tag; do
    # ローカルTAGファイルに存在しないTAGを取得
    if ! grep -Fxq "${server_tag}" ${CREATED_INDEX_TAG_FILE}; then
        MISSING_TAGS="${MISSING_TAGS}${server_tag}\n"
    fi
done < ${TEMP_SORTED_SERVER_TAG_FILE}

# 末尾の改行を削除
MISSING_TAGS=$(echo -e "${MISSING_TAGS}" | sed '$d')

if [ -z "$(echo -e "${MISSING_TAGS}")" ]; then
    echo "不足しているTAGはありません。スクリプトを終了します。"
    exit 0
else
    echo "不足しているTAGリスト:"
    echo -e "${MISSING_TAGS}"
fi

# MISSING_TAGS を一時ファイルに保存
echo -e "${MISSING_TAGS}" > ${TEMP_MISSING_TAGS_FILE}

# 不足しているTAGでn8nフローを実行
echo "不足しているTAGでn8nフローを実行します..."
HAS_ERROR=0
while IFS= read -r TAG; do
    # TAG形式(NNN-YYYYMMDD)を分割して番号と日付に格納
    TAG_NUMBER="${TAG%%-*}"
    TAG_DATE="${TAG#*-}"

    if [ -z "${TAG_NUMBER}" ] || [ -z "${TAG_DATE}" ] || [ "${TAG_NUMBER}" = "${TAG}" ] || [ "${TAG_DATE}" = "${TAG}" ]; then
        echo "TAG形式が不正です: TAG=${TAG}"
        HAS_ERROR=1
        continue
    fi

    TAG_NUMBER_LENGTH=${#TAG_NUMBER}

    if ! [[ "${TAG_NUMBER}" =~ ^[0-9]+$ ]]; then
        echo "TAG番号が数値ではありません: TAG=${TAG}"
        HAS_ERROR=1
        continue
    fi

    if ! [[ "${TAG_DATE}" =~ ^[0-9]{8}$ ]]; then
        echo "TAG日付の形式が不正です: TAG=${TAG}"
        HAS_ERROR=1
        continue
    fi

    TAG_NUMBER_INT=$((10#${TAG_NUMBER}))
    if [ "${TAG_NUMBER_INT}" -le 0 ]; then
        echo "TAG番号が0以下のため旧タグ番号を計算できません: TAG=${TAG}"
        HAS_ERROR=1
        continue
    fi

    OLD_TAG_INT=$((TAG_NUMBER_INT - 1))
    OLD_TAG_NUMBER=$(printf "%0${TAG_NUMBER_LENGTH}d" "${OLD_TAG_INT}")

    # 実行環境ごとにループ
    for ENV in "${WORK_ENVS[@]}"; do
        # 環境ごとのログファイル（日付別に成功・失敗を分割）
        CURRENT_DATE=$(date '+%Y%m%d')
        SUCCESS_LOG_FILE="${LOG_DIR}/${CURRENT_DATE}_n8n_${ENV}_success.log"
        ERROR_LOG_FILE="${LOG_DIR}/${CURRENT_DATE}_n8n_${ENV}_error.log"

        echo "n8nフローを実行します: TAG=${TAG}, WORK_ENV=${ENV}..."

        # ---------- URL1 実行 ----------
        RESPONSE1=$(curl -s --connect-timeout 120 --max-time 0 -w "%{http_code}" -o "${TEMP_N8N_RESPONSE}" \
            -X POST -H "Content-Type: application/json" \
            -d "{\"newTag\":\"${TAG_NUMBER}\",\"gitUser\":\"${GIT_USER}\",\"gitToken\":\"${GIT_TOKEN}\",\"workEnv\":\"${ENV}\",\"indexNameShort\":\"${INDEX_NAME_SHORT}\"}" \
            "${N8N_FLOW_URL1}")

        BODY1=$(cat "${TEMP_N8N_RESPONSE}")
        TS=$(date '+%Y-%m-%d %H:%M:%S')

        if [ "${RESPONSE1}" -ne 200 ]; then
            echo "n8nフロー(URL1) が失敗しました: TAG=${TAG}, WORK_ENV=${ENV}"
            echo "レスポンス内容:"
            echo "${BODY1}"

            echo "${TS} {URL1 実行のレスポンス:${BODY1}, URL2 実行のレスポンス:実行前に失敗}" >> "${ERROR_LOG_FILE}"

            HAS_ERROR=1
            continue
        fi

        # ---------- URL2 実行 ----------
        RESPONSE2=$(curl -s --connect-timeout 120 --max-time 0 -w "%{http_code}" -o "${TEMP_N8N_RESPONSE}" \
            -X POST -H "Content-Type: application/json" \
            -d "{\"newTag\":\"${TAG_NUMBER}\",\"newTagDate\":\"${TAG_DATE}\",\"oldTagDate\":\"${TAG_DATE}\",\"gitUser\":\"${GIT_USER}\",\"gitToken\":\"${GIT_TOKEN}\",\"workEnv\":\"${ENV}\",\"indexNameShort\":\"${INDEX_NAME_SHORT}\"}" \
            "${N8N_FLOW_URL2}")

        BODY2=$(cat "${TEMP_N8N_RESPONSE}")
        TS=$(date '+%Y-%m-%d %H:%M:%S')

        if [ "${RESPONSE2}" -ne 200 ]; then
            echo "n8nフロー(URL2) が失敗しました: TAG=${TAG}, WORK_ENV=${ENV}"
            echo "レスポンス内容:"
            echo "${BODY2}"

            echo "${TS} {URL1 実行のレスポンス:${BODY1}, URL2 実行のレスポンス:${BODY2}}" >> "${ERROR_LOG_FILE}"

            HAS_ERROR=1
            continue
        fi

        # 両方成功したらローカルTAGファイルに追加 & ログ出力
        echo "n8nフロー(URL1 + URL2) が成功しました: TAG=${TAG}, WORK_ENV=${ENV}"
        echo "${TAG}" >> "${CREATED_INDEX_TAG_FILE}"

        TS=$(date '+%Y-%m-%d %H:%M:%S')
        echo "${TS} {URL1 実行のレスポンス:${BODY1}, URL2 実行のレスポンス:${BODY2}}" >> "${SUCCESS_LOG_FILE}"
    done
done < "${TEMP_MISSING_TAGS_FILE}"



# 一時的なファイルの削除
rm -f ${TEMP_SERVER_TAG_FILE}
rm -f ${TEMP_SORTED_SERVER_TAG_FILE}
rm -f ${TEMP_MISSING_TAGS_FILE}
rm -f ${TEMP_N8N_RESPONSE}

if [ "${HAS_ERROR}" -eq 0 ]; then
    echo "全ての不足しているTAGを正常に処理しました。ローカルTAGファイルを更新しました。"
    echo "スクリプトの実行が完了しました。"
    exit 0
else
    echo "一部の環境でエラーが発生しました。詳細はログファイルを確認してください。"
    exit 1
fi
