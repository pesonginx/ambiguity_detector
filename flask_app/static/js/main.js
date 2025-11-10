/**
 * ファイルアップローダー - メインJavaScript
 * SSE、リアルタイム更新、ロック状態チェック
 */

// グローバル変数
let eventSource = null;
let lockCheckInterval = null;
let currentTaskId = null;

// DOMロード完了時の初期化
document.addEventListener('DOMContentLoaded', function() {
    initializeUploader();
});

/**
 * アップローダーの初期化
 */
function initializeUploader() {
    const fileInput = document.getElementById('fileInput');
    const fileUploadForm = document.getElementById('fileUploadForm');
    
    if (!fileInput || !fileUploadForm) {
        return; // アップロードページでない場合
    }
    
    // ファイル選択時の処理
    fileInput.addEventListener('change', handleFileSelect);
    
    // ファイル選択ボタンのクリック処理
    const selectFileBtn = document.querySelector('.btn-select-file');
    if (selectFileBtn) {
        selectFileBtn.addEventListener('click', function() {
            fileInput.click();
        });
    }
    
    // フォーム送信時の処理
    fileUploadForm.addEventListener('submit', handleFormSubmit);
    
    // 新規アップロードボタン
    const newUploadBtn = document.getElementById('newUploadBtn');
    if (newUploadBtn) {
        newUploadBtn.addEventListener('click', resetUploader);
    }
    
    // ロック状態のチェックを開始
    checkLockStatus();
    startLockStatusCheck();
}

/**
 * ファイル選択時の処理
 */
function handleFileSelect(event) {
    const file = event.target.files[0];
    const fileNameDisplay = document.getElementById('fileName');
    
    if (file) {
        fileNameDisplay.textContent = file.name;
        fileNameDisplay.style.color = '#1e293b';
    } else {
        fileNameDisplay.textContent = 'ファイルを選択してください';
        fileNameDisplay.style.color = '#64748b';
    }
}

/**
 * フォーム送信処理
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    
    const uploadBtn = document.getElementById('uploadBtn');
    const formData = new FormData(event.target);
    
    // ボタンを無効化
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'アップロード中...';
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            // アップロード成功
            currentTaskId = data.task_id;
            showProcessingSection();
            startStreaming(data.task_id);
        } else {
            // エラー
            alert('エラー: ' + data.error);
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'アップロード開始';
        }
    } catch (error) {
        console.error('アップロードエラー:', error);
        alert('アップロードに失敗しました: ' + error.message);
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'アップロード開始';
    }
}

/**
 * 処理セクションを表示
 */
function showProcessingSection() {
    const uploadForm = document.getElementById('uploadForm');
    const processingSection = document.getElementById('processingSection');
    
    uploadForm.style.display = 'none';
    processingSection.style.display = 'block';
    
    // 初期化
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('logOutput').innerHTML = '';
    document.getElementById('currentStep').innerHTML = '';
    document.getElementById('resultMessage').style.display = 'none';
}

/**
 * SSEでログをストリーミング
 */
function startStreaming(taskId) {
    const logOutput = document.getElementById('logOutput');
    const currentStep = document.getElementById('currentStep');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    
    // EventSourceを作成
    eventSource = new EventSource(`/api/stream/${taskId}`);
    
    let isProcessingComplete = false;
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            // 最終ステータスをチェック
            if (data.is_final === true && data.status) {
                // 処理完了
                isProcessingComplete = true;
                eventSource.close();
                showResult(data.status, data.duration, data.error_message);
                stopLockStatusCheck();
                checkLockStatus(); // 即座に更新
            } else {
                // ログエントリーを追加
                addLogEntry(logOutput, data);
                
                // 進捗バーを更新
                if (data.progress !== undefined && data.progress !== null) {
                    updateProgress(progressFill, progressPercent, data.progress);
                }
                
                // 現在のステップを更新
                if (data.level === 'INFO' && !data.message.includes('成功')) {
                    updateCurrentStep(currentStep, data);
                } else if (data.level === 'WARNING' || data.level === 'ERROR') {
                    // エラーや警告の場合も現在のステップに表示
                    updateCurrentStep(currentStep, data);
                }
            }
            
            // ログを自動スクロール
            logOutput.scrollTop = logOutput.scrollHeight;
        } catch (error) {
            console.error('ログパースエラー:', error, event.data);
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSEエラー:', error);
        eventSource.close();
        
        // 正常終了済みの場合はエラーメッセージを表示しない
        if (!isProcessingComplete) {
            showResult('error', 0, 'ストリーミング接続が切断されました');
            stopLockStatusCheck();
            checkLockStatus();
        }
    };
}

/**
 * ログエントリーを追加
 */
function addLogEntry(container, data) {
    const logLine = document.createElement('div');
    const levelColor = data.level === 'WARNING' ? '#fbbf24' : 
                       data.level === 'ERROR' ? '#ef4444' : '#10b981';
    
    // エラーレベルに応じて背景色を設定
    let backgroundColor = 'transparent';
    if (data.level === 'ERROR') {
        backgroundColor = 'rgba(239, 68, 68, 0.15)';
    } else if (data.level === 'WARNING') {
        backgroundColor = 'rgba(251, 191, 36, 0.15)';
    }
    
    logLine.style.backgroundColor = backgroundColor;
    logLine.style.padding = '0.25rem 0.5rem';
    logLine.style.borderRadius = '0.25rem';
    logLine.style.marginBottom = '0.25rem';
    
    logLine.innerHTML = `<span style="color: #94a3b8;">${data.timestamp}</span> ` +
                       `<span style="color: ${levelColor}; font-weight: bold;">[${data.level}]</span> ` +
                       `<span style="color: #f1f5f9;">${data.step_name}: ${data.message}</span>`;
    
    container.appendChild(logLine);
}

/**
 * 進捗バーを更新
 */
function updateProgress(progressFill, progressPercent, progress) {
    progressFill.style.width = progress + '%';
    progressPercent.textContent = progress + '%';
}

/**
 * 現在のステップを更新
 */
function updateCurrentStep(container, data) {
    const elapsed = calculateElapsedTime();
    const levelColor = data.level === 'ERROR' ? '#ef4444' : 
                       data.level === 'WARNING' ? '#fbbf24' : '#10b981';
    const borderColor = data.level === 'ERROR' ? '#ef4444' : 
                        data.level === 'WARNING' ? '#fbbf24' : '#fbbf24';
    const levelText = data.level === 'ERROR' ? 'エラー' : 
                      data.level === 'WARNING' ? '警告' : '現在の処理';
    
    container.innerHTML = `<div style="border-top: 2px solid ${borderColor}; padding-top: 1rem;">` +
                         `<div style="color: ${levelColor};">${elapsed} [${levelText}] ${data.step_name}: ${data.message}</div>` +
                         `<div style="margin-top: 0.5rem;">${data.progress || 0}% ${'|'.repeat(Math.floor((data.progress || 0) / 2))}</div>` +
                         `</div>`;
}

/**
 * 経過時間を計算（ダミー）
 */
function calculateElapsedTime() {
    const now = new Date();
    return now.toTimeString().split(' ')[0];
}

/**
 * 結果を表示
 */
function showResult(status, duration, errorMessage) {
    const resultMessage = document.getElementById('resultMessage');
    const viewLogsBtn = document.getElementById('viewLogsBtn');
    const newUploadBtn = document.getElementById('newUploadBtn');
    const currentStep = document.getElementById('currentStep');
    
    // 現在のステップをクリア
    currentStep.innerHTML = '';
    
    if (status === 'completed') {
        resultMessage.className = 'result-message success';
        resultMessage.innerHTML = `<strong>✓ 成功</strong><br>` +
                                 `すべての処理が正常に終了しました。<br>` +
                                 `所要時間: ${duration.toFixed(2)}秒`;
        
        // 進捗バーを100%に
        const progressFill = document.getElementById('progressFill');
        progressFill.style.width = '100%';
        progressFill.style.background = 'linear-gradient(90deg, #10b981, #34d399)';
        document.getElementById('progressPercent').textContent = '100%';
    } else {
        resultMessage.className = 'result-message error';
        resultMessage.innerHTML = `<strong>✗ エラー</strong><br>` +
                                 `処理中にエラーが発生しました。<br>` +
                                 (errorMessage ? `詳細: ${errorMessage}` : '');
        
        // 進捗バーを赤色に変更
        const progressFill = document.getElementById('progressFill');
        progressFill.style.background = 'linear-gradient(90deg, #ef4444, #f87171)';
    }
    
    resultMessage.style.display = 'block';
    viewLogsBtn.style.display = 'inline-block';
    newUploadBtn.style.display = 'inline-block';
    
    // ログ表示ボタンのリンクを設定
    viewLogsBtn.onclick = function() {
        window.location.href = `/logs/${currentTaskId}`;
    };
}

/**
 * アップローダーをリセット
 */
function resetUploader() {
    const uploadForm = document.getElementById('uploadForm');
    const processingSection = document.getElementById('processingSection');
    const fileUploadForm = document.getElementById('fileUploadForm');
    const fileNameDisplay = document.getElementById('fileName');
    const uploadBtn = document.getElementById('uploadBtn');
    
    // フォームをリセット
    fileUploadForm.reset();
    fileNameDisplay.textContent = 'ファイルを選択してください';
    fileNameDisplay.style.color = '#64748b';
    uploadBtn.disabled = false;
    uploadBtn.textContent = 'アップロード開始';
    
    // 表示を切り替え
    processingSection.style.display = 'none';
    uploadForm.style.display = 'block';
    
    // EventSourceをクローズ
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    currentTaskId = null;
}

/**
 * ロック状態をチェック
 */
async function checkLockStatus() {
    try {
        const response = await fetch('/api/lock_status');
        const data = await response.json();
        
        const lockMessage = document.getElementById('lockMessage');
        const uploadForm = document.getElementById('uploadForm');
        const uploadBtn = document.getElementById('uploadBtn');
        
        if (data.is_locked) {
            // ロック中
            if (lockMessage) {
                lockMessage.style.display = 'block';
            }
            if (uploadForm && data.current_task_id !== currentTaskId) {
                // 他のタスクが実行中の場合のみフォームを無効化
                uploadForm.style.opacity = '0.5';
                uploadForm.style.pointerEvents = 'none';
            }
            if (uploadBtn) {
                uploadBtn.disabled = true;
            }
        } else {
            // ロック解除
            if (lockMessage) {
                lockMessage.style.display = 'none';
            }
            if (uploadForm) {
                uploadForm.style.opacity = '1';
                uploadForm.style.pointerEvents = 'auto';
            }
            if (uploadBtn && !currentTaskId) {
                uploadBtn.disabled = false;
            }
        }
    } catch (error) {
        console.error('ロック状態チェックエラー:', error);
    }
}

/**
 * ロック状態チェックを開始
 */
function startLockStatusCheck() {
    // 既存のインターバルをクリア
    if (lockCheckInterval) {
        clearInterval(lockCheckInterval);
    }
    
    // 2秒ごとにチェック
    lockCheckInterval = setInterval(checkLockStatus, 2000);
}

/**
 * ロック状態チェックを停止
 */
function stopLockStatusCheck() {
    if (lockCheckInterval) {
        clearInterval(lockCheckInterval);
        lockCheckInterval = null;
    }
}

// ページを離れる時のクリーンアップ
window.addEventListener('beforeunload', function() {
    if (eventSource) {
        eventSource.close();
    }
    stopLockStatusCheck();
});

