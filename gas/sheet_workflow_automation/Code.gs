/**
 * Googleスプレッドシート業務自動化テンプレート（GAS）
 *
 * 機能:
 * - 指定シートから「通知対象ステータス」かつ「未通知」の行だけを抽出
 * - LockServiceによる二重実行・二重送信の防止
 * - Webhook（Slack / Chatwork / Discord等）またはGmail通知
 * - 送信日時・エラー内容を実行ログシートへ自動記録
 */

const CONFIG = {
  DATA_SHEET_NAME: "案件管理",
  LOG_SHEET_NAME: "実行ログ",
  TARGET_STATUS: "承認済",
  DONE_MARK: "送信済",
  // 列番号（1始まり）
  COL_ID: 1,
  COL_TITLE: 2,
  COL_OWNER: 3,
  COL_STATUS: 4,
  COL_NOTIFIED_FLAG: 5,
  COL_NOTIFIED_AT: 6,
  // 通知先（スクリプトプロパティで安全に管理）
  PROP_WEBHOOK_URL: "NOTIFICATION_WEBHOOK_URL",
  PROP_NOTIFY_EMAIL: "NOTIFICATION_EMAIL",
};

/**
 * 定期トリガー（5分〜15分おき）から呼び出すメイン関数
 */
function runNotificationBatch() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    appendLog_("SKIP", "別の処理が実行中のためスキップしました");
    return;
  }

  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(CONFIG.DATA_SHEET_NAME);
    if (!sheet) {
      throw new Error(`シート「${CONFIG.DATA_SHEET_NAME}」が見つかりません`);
    }

    const lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      return;
    }

    const values = sheet.getRange(2, 1, lastRow - 1, CONFIG.COL_NOTIFIED_AT).getValues();
    let sentCount = 0;

    for (let i = 0; i < values.length; i++) {
      const rowNum = i + 2;
      const row = values[i];
      const id = String(row[CONFIG.COL_ID - 1] || "").trim();
      const title = String(row[CONFIG.COL_TITLE - 1] || "").trim();
      const owner = String(row[CONFIG.COL_OWNER - 1] || "").trim();
      const status = String(row[CONFIG.COL_STATUS - 1] || "").trim();
      const notified = String(row[CONFIG.COL_NOTIFIED_FLAG - 1] || "").trim();

      if (!id || status !== CONFIG.TARGET_STATUS || notified === CONFIG.DONE_MARK) {
        continue;
      }

      const message = buildMessage_(id, title, owner, status);
      dispatchNotification_(message, `[自動通知] ${id}: ${title}`);

      const nowStr = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd HH:mm:ss");
      sheet.getRange(rowNum, CONFIG.COL_NOTIFIED_FLAG).setValue(CONFIG.DONE_MARK);
      sheet.getRange(rowNum, CONFIG.COL_NOTIFIED_AT).setValue(nowStr);
      sentCount++;
    }

    if (sentCount > 0) {
      appendLog_("OK", `${sentCount}件の通知を送信しました`);
    }
  } catch (err) {
    appendLog_("ERROR", err && err.message ? err.message : String(err));
    throw err;
  } finally {
    lock.releaseLock();
  }
}

function buildMessage_(id, title, owner, status) {
  return [
    "【ステータス更新通知】",
    `ID: ${id}`,
    `件名: ${title || "(未入力)"}`,
    `担当: ${owner || "(未設定)"}`,
    `ステータス: ${status}`,
  ].join("\n");
}

function dispatchNotification_(message, subject) {
  const props = PropertiesService.getScriptProperties();
  const webhookUrl = props.getProperty(CONFIG.PROP_WEBHOOK_URL);
  const email = props.getProperty(CONFIG.PROP_NOTIFY_EMAIL);

  if (webhookUrl) {
    const res = UrlFetchApp.fetch(webhookUrl, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ text: message }),
      muteHttpExceptions: true,
    });
    const code = res.getResponseCode();
    if (code < 200 || code >= 300) {
      throw new Error(`Webhook送信失敗 (HTTP ${code}): ${res.getContentText()}`);
    }
    return;
  }

  if (email) {
    MailApp.sendEmail({ to: email, subject: subject, body: message });
    return;
  }

  throw new Error("通知先が未設定です。スクリプトプロパティを設定してください。");
}

function appendLog_(level, detail) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let logSheet = ss.getSheetByName(CONFIG.LOG_SHEET_NAME);
  if (!logSheet) {
    logSheet = ss.insertSheet(CONFIG.LOG_SHEET_NAME);
    logSheet.appendRow(["日時", "レベル", "内容"]);
  }
  const nowStr = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd HH:mm:ss");
  logSheet.appendRow([nowStr, level, detail]);
}
