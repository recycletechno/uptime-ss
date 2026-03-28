/**
 * Checks all active bots in the "Control" sheet.
 * If a bot's timestamp is stale (older than its mins_to_alert), sends a Telegram alert.
 * If a bot recovers, sends a recovery message.
 *
 * Sheet columns:
 *   A: bot name, B: datetime, C: active, D: tg_sent,
 *   E: chat_id, F: notify, G: mins_to_alert
 *
 * Set up a time-driven trigger to run this every 5 minutes.
 */

var TG_TOKEN = "YOUR_TOKEN_HERE";  // Replace with your actual bot token

function checkBots() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Control");
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var data = sheet.getRange(2, 1, lastRow - 1, 7).getValues();
  var nowUtc = new Date();

  for (var i = 0; i < data.length; i++) {
    var botName = data[i][0];
    var botDatetime = data[i][1];
    var active = data[i][2];
    var tgSent = data[i][3];
    var chatId = data[i][4];
    var notify = data[i][5];
    var minsToAlert = data[i][6];

    if (!active || !botDatetime || !minsToAlert) continue;
    if (typeof botDatetime.getTime !== "function") continue;

    var diffMins = (nowUtc.getTime() - botDatetime.getTime()) / 60000;
    var formattedDate = Utilities.formatDate(botDatetime, "GMT", "dd-MM-yyyy HH:mm:ss");
    var rowIndex = i + 2;

    if (diffMins > minsToAlert) {
      if (tgSent == 0) {
        sendTelegram(
          "Bot [" + botName + "] stopped updating since " + formattedDate + " " + notify,
          chatId
        );
        sheet.getRange(rowIndex, 4).setValue(1);
      }
    } else {
      if (tgSent == 1) {
        sendTelegram(
          "Bot [" + botName + "] resumed at " + formattedDate + " " + notify,
          chatId
        );
        sheet.getRange(rowIndex, 4).setValue(0);
      }
    }
  }
}

function sendTelegram(message, chatId) {
  var url = "https://api.telegram.org/bot" + TG_TOKEN
    + "/sendMessage?chat_id=" + encodeURIComponent(chatId)
    + "&text=" + encodeURIComponent(message);
  UrlFetchApp.fetch(url);
}
