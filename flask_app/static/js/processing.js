/**
 * processing.js - 処理状況ページのJavaScript
 * SSEでリアルタイム更新、ステップ進捗表示、統計情報表示
 */

let eventSource = null;
let startTime = null;
let elapsedInterval = null;

/**
 * 処理の初期化とストリーミング開始
 */
function initProcessing(taskId) {
    console.log('Processing initialized for task:', taskId);
    
    // 経過時間の更新を開始
    startElapsedTimeCounter();
    
    // SSEでログとステップ進捗をストリーミング
    startEventStream(taskId);
}

/**
 * 経過時間カウンターを開始
 */
function startElapsedTimeCounter() {
    const startTimeElement = document.getElementById('startTime');
    if (startTimeElement && startTimeElement.textContent !== '-') {
        startTime = new Date(startTimeElement.textContent);
    } else {
        startTime = new Date();
    }
    
    // 1秒ごとに経過時間を更新
    elapsedInterval = setInterval(updateElapsedTime, 1000);
    updateElapsedTime();
}

/**
 * 経過時間を更新
 */
function updateElapsedTime() {
    if (!startTime) return;
    
    const now = new Date();
    const elapsed = Math.floor((now - startTime) / 1000);
    
    const hours = Math.floor(elapsed / 3600);
    const minutes = Math.floor((elapsed % 3600) / 60);
    const seconds = elapsed % 60;
    
    const elapsedTimeElement = document.getElementById('elapsedTime');
    if (elapsedTimeElement) {
        if (hours > 0) {
            elapsedTimeElement.textContent = `${hours}時間${minutes}分${seconds}秒`;
        } else if (minutes > 0) {
            elapsedTimeElement.textContent = `${minutes}分${seconds}秒`;
        } else {
            elapsedTimeElement.textContent = `${seconds}秒`;
        }
    }
}

/**
 * EventSourceでストリーミング開始
 */
function startEventStream(taskId) {
    const logContainer = document.getElementById('logContainer');
    
    eventSource = new EventSource(`/api/stream/${taskId}`);
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            if (data.error) {
                console.error('Stream error:', data.error);
                showError('ストリーミング接続エラー: ' + data.error);
                return;
            }
            
            // データタイプに応じて処理
            switch(data.type) {
                case 'log':
                    addLogEntry(logContainer, data);
                    break;
                    
                case 'step_progress':
                    updateStepProgress(data);
                    updateStatistics(data);
                    break;
                    
                case 'final':
                    handleFinalStatus(data);
                    break;
            }
            
            // ログコンテナを自動スクロール
            logContainer.scrollTop = logContainer.scrollHeight;
            
        } catch (error) {
            console.error('Parse error:', error, event.data);
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE error:', error);
        eventSource.close();
        
        // エラーメッセージを表示
        const statusBadge = document.getElementById('statusBadge');
        if (statusBadge && !statusBadge.classList.contains('status-completed')) {
            statusBadge.textContent = '接続エラー';
            statusBadge.className = 'status-badge status-error';
        }
    };
}

/**
 * ログエントリーを追加
 */
function addLogEntry(container, data) {
    const logLine = document.createElement('div');
    logLine.className = 'log-line';
    
    // レベルに応じてクラスを追加
    if (data.level === 'ERROR') {
        logLine.classList.add('error');
    } else if (data.level === 'WARNING') {
        logLine.classList.add('warning');
    }
    
    // ログの色を設定
    const levelColor = data.level === 'ERROR' ? '#ef4444' :
                       data.level === 'WARNING' ? '#fbbf24' : '#10b981';
    
    logLine.innerHTML = `<span style="color: #94a3b8;">${data.timestamp}</span> ` +
                       `<span style="color: ${levelColor}; font-weight: bold;">[${data.level}]</span> ` +
                       `<span style="color: #f1f5f9;">${data.step_name}: ${data.message}</span>`;
    
    container.appendChild(logLine);
}

/**
 * ステップ進捗を更新
 */
function updateStepProgress(data) {
    // 現在のステップ名
    const stepNameElement = document.getElementById('currentStepName');
    if (stepNameElement && data.current_step) {
        stepNameElement.textContent = data.current_step;
    }
    
    // ステップインデックス
    const stepIndexElement = document.getElementById('currentStepIndex');
    if (stepIndexElement) {
        stepIndexElement.textContent = data.current_step_index || 0;
    }
    
    // 総ステップ数
    const totalStepsElement = document.getElementById('totalSteps');
    if (totalStepsElement) {
        totalStepsElement.textContent = data.total_steps || 10;
    }
    
    // 残りステップ数
    const remainingStepsElement = document.getElementById('remainingSteps');
    if (remainingStepsElement) {
        const remaining = (data.total_steps || 10) - (data.current_step_index || 0);
        remainingStepsElement.textContent = remaining;
    }
    
    // ステップ進捗バー
    const stepProgressBar = document.getElementById('stepProgressBar');
    const stepProgressPercent = document.getElementById('stepProgressPercent');
    if (stepProgressBar && stepProgressPercent) {
        const progress = Math.min(100, Math.max(0, data.step_progress || 0));
        stepProgressBar.style.width = progress + '%';
        stepProgressPercent.textContent = Math.round(progress) + '%';
    }
    
    // 推定残り時間
    updateEstimatedTime(data.estimated_remaining_time || 0);
}

/**
 * 推定残り時間を更新
 */
function updateEstimatedTime(seconds) {
    const estimatedTimeElement = document.getElementById('estimatedTime');
    const remainingTimeDisplay = document.getElementById('remainingTimeDisplay');
    const estimatedCompletionTime = document.getElementById('estimatedCompletionTime');
    
    if (seconds <= 0) {
        if (estimatedTimeElement) {
            estimatedTimeElement.textContent = '推定残り時間: 計算中...';
        }
        if (remainingTimeDisplay) {
            remainingTimeDisplay.textContent = '計算中...';
        }
        if (estimatedCompletionTime) {
            estimatedCompletionTime.textContent = '計算中...';
        }
        return;
    }
    
    // 残り時間を人間が読める形式に変換
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    let timeString = '';
    if (hours > 0) {
        timeString = `約${hours}時間${minutes}分`;
    } else if (minutes > 0) {
        timeString = `約${minutes}分${secs}秒`;
    } else {
        timeString = `約${secs}秒`;
    }
    
    if (estimatedTimeElement) {
        estimatedTimeElement.textContent = `推定残り時間: ${timeString}`;
    }
    
    if (remainingTimeDisplay) {
        remainingTimeDisplay.textContent = timeString;
    }
    
    // 推定完了時刻を計算
    if (estimatedCompletionTime) {
        const completionTime = new Date(Date.now() + seconds * 1000);
        const timeStr = completionTime.toLocaleTimeString('ja-JP', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
        estimatedCompletionTime.textContent = timeStr;
    }
}

/**
 * 統計情報を更新
 */
function updateStatistics(data) {
    // レコード数
    const recordCountElement = document.getElementById('recordCount');
    if (recordCountElement && data.record_count !== undefined) {
        animateNumber(recordCountElement, data.record_count);
    }
    
    // 生成JSONファイル数
    const jsonCreatedElement = document.getElementById('jsonFilesCreated');
    if (jsonCreatedElement && data.json_files_created !== undefined) {
        animateNumber(jsonCreatedElement, data.json_files_created);
    }
    
    // 削除JSONファイル数
    const jsonDeletedElement = document.getElementById('jsonFilesDeleted');
    if (jsonDeletedElement && data.json_files_deleted !== undefined) {
        animateNumber(jsonDeletedElement, data.json_files_deleted);
    }
}

/**
 * 数値をアニメーション付きで更新
 */
function animateNumber(element, targetValue) {
    const currentValue = parseInt(element.textContent) || 0;
    
    if (currentValue === targetValue) return;
    
    // アニメーションなしで即座に更新（パフォーマンスのため）
    element.textContent = targetValue.toLocaleString();
}

/**
 * 最終ステータスを処理
 */
function handleFinalStatus(data) {
    console.log('Final status:', data);
    
    // EventSourceをクローズ
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    // 経過時間カウンターを停止
    if (elapsedInterval) {
        clearInterval(elapsedInterval);
        elapsedInterval = null;
    }
    
    // ステータスバッジを更新
    const statusBadge = document.getElementById('statusBadge');
    const spinner = document.querySelector('.loading-spinner');
    
    if (data.status === 'completed') {
        if (statusBadge) {
            statusBadge.textContent = '完了';
            statusBadge.className = 'status-badge status-completed';
        }
        if (spinner) {
            spinner.style.display = 'none';
        }
        
        // 進捗バーを100%に
        const stepProgressBar = document.getElementById('stepProgressBar');
        const stepProgressPercent = document.getElementById('stepProgressPercent');
        if (stepProgressBar) {
            stepProgressBar.style.width = '100%';
            stepProgressBar.style.background = 'linear-gradient(90deg, #10b981, #34d399)';
        }
        if (stepProgressPercent) {
            stepProgressPercent.textContent = '100%';
        }
        
        // 残り時間を0に
        updateEstimatedTime(0);
        const remainingTimeDisplay = document.getElementById('remainingTimeDisplay');
        if (remainingTimeDisplay) {
            remainingTimeDisplay.textContent = '完了';
        }
        
        // 残りステップを0に
        const remainingSteps = document.getElementById('remainingSteps');
        if (remainingSteps) {
            remainingSteps.textContent = '0';
        }
        
    } else if (data.status === 'error') {
        if (statusBadge) {
            statusBadge.textContent = 'エラー';
            statusBadge.className = 'status-badge status-error';
        }
        if (spinner) {
            spinner.style.display = 'none';
        }
        
        // 進捗バーを赤色に
        const stepProgressBar = document.getElementById('stepProgressBar');
        if (stepProgressBar) {
            stepProgressBar.style.background = 'linear-gradient(90deg, #ef4444, #f87171)';
        }
        
        // エラーメッセージを表示
        if (data.error_message) {
            const logContainer = document.getElementById('logContainer');
            const errorLog = document.createElement('div');
            errorLog.className = 'log-line error';
            errorLog.innerHTML = `<span style="color: #ef4444; font-weight: bold;">[ERROR]</span> ` +
                                `<span style="color: #f1f5f9;">${data.error_message}</span>`;
            logContainer.appendChild(errorLog);
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }
    
    // 処理時間を表示
    if (data.duration) {
        const elapsedTimeElement = document.getElementById('elapsedTime');
        if (elapsedTimeElement) {
            const hours = Math.floor(data.duration / 3600);
            const minutes = Math.floor((data.duration % 3600) / 60);
            const seconds = Math.floor(data.duration % 60);
            
            if (hours > 0) {
                elapsedTimeElement.textContent = `${hours}時間${minutes}分${seconds}秒`;
            } else if (minutes > 0) {
                elapsedTimeElement.textContent = `${minutes}分${seconds}秒`;
            } else {
                elapsedTimeElement.textContent = `${seconds}秒`;
            }
        }
    }
    
    // アクションボタンを表示
    const actionButtons = document.getElementById('actionButtons');
    if (actionButtons) {
        actionButtons.style.display = 'flex';
    }
}

/**
 * エラーメッセージを表示
 */
function showError(message) {
    const logContainer = document.getElementById('logContainer');
    if (logContainer) {
        const errorLog = document.createElement('div');
        errorLog.className = 'log-line error';
        errorLog.innerHTML = `<span style="color: #ef4444; font-weight: bold;">[ERROR]</span> ` +
                            `<span style="color: #f1f5f9;">${message}</span>`;
        logContainer.appendChild(errorLog);
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

/**
 * ページを離れる時のクリーンアップ
 */
window.addEventListener('beforeunload', function() {
    if (eventSource) {
        eventSource.close();
    }
    if (elapsedInterval) {
        clearInterval(elapsedInterval);
    }
});

