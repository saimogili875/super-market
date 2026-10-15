(function() {
  var dataElement = document.getElementById('table-data');
  if (!dataElement) return;
  var data = JSON.parse(dataElement.textContent);

  var wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
  var wsUrl = wsScheme + "://" + window.location.host + "/ws/tables/" + data.qrToken + "/";
  var socket = null;
  var reconnectTimer = null;
  var attempts = 0;
  var maxAttempts = 15;
  var initialDelay = 2000;
  var maxDelay = 30000;
  var currentDelay = initialDelay;
  var wasDisconnected = false;

  function connect() {
    try {
      socket = new WebSocket(wsUrl);
    } catch (err) {
      scheduleReconnect();
      return;
    }

    socket.onopen = function() {
      console.log("Realtime table status connected.");
      if (wasDisconnected) {
        // Reconnected after a dropped connection: reload page to ensure state isn't stale
        window.location.reload();
        return;
      }
      attempts = 0;
      currentDelay = initialDelay;
    };

    socket.onmessage = function(event) {
      var msgData = JSON.parse(event.data);
      if (msgData.type === "order.status" || msgData.type === "table.paid") {
        window.location.reload();
      }
    };

    socket.onclose = function() {
      console.log("Realtime table connection closed.");
      wasDisconnected = true;
      scheduleReconnect();
    };

    socket.onerror = function() {
      // socket.onclose fires after onerror
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    if (attempts >= maxAttempts) {
      console.log("Max reconnect attempts reached for table status.");
      showOfflinePrompt();
      return;
    }

    attempts++;
    var wait = currentDelay;
    currentDelay = Math.min(currentDelay * 2, maxDelay);

    reconnectTimer = setTimeout(function() {
      connect();
    }, wait);
  }

  function showOfflinePrompt() {
    var container = document.getElementById("status-container") || document.body;
    if (document.getElementById("table-offline-prompt")) return;

    var prompt = document.createElement("div");
    prompt.id = "table-offline-prompt";
    prompt.className = "card my-4";
    prompt.style.cssText = "padding: 12px 16px; background-color: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; color: #ef4444; font-size: 0.875rem; text-align: center;";
    prompt.innerHTML = 'Realtime updates disconnected. <button onclick="window.location.reload()" style="background: none; border: none; color: inherit; text-decoration: underline; cursor: pointer; font-weight: bold; padding: 0;">Click here to refresh</button> for current status.';
    container.prepend(prompt);
  }

  connect();
})();

