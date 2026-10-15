/**
 * Order Tracker — live updates + chat over the order WebSocket room.
 *
 * Connects to ws/orders/<orderId>/ and updates #order-status-display
 * and appends chat bubbles to #message-thread.
 *
 * CSP-safe: loaded as an external file via {% static %} + defer, using
 * standard DOM event listeners (no eval or inline handlers).
 */
(function() {
  function initOrderTracker() {
    var container = document.getElementById("order-tracker-container");
    if (!container) return;

    var orderId = container.getAttribute("data-order-id");
    var status = container.getAttribute("data-initial-status");
    var labelsEl = document.getElementById("status-labels");
    var labels = labelsEl ? JSON.parse(labelsEl.textContent) : {};

    var statusDisplay = document.getElementById("order-status-display");
    var offlineWarning = document.getElementById("offline-warning");

    var STEPS = [
      "PLACED",
      "APPROVED",
      "KITCHEN",
      "READY",
      "DISPATCH",
      "ARRIVED",
      "COLLECT"
    ];

    function updateTimeline(newStatus) {
      var cancelledNotice = document.getElementById("cancelled-notice");
      var timelineWrapper = document.getElementById("timeline-wrapper");
      var paymentBadge = document.getElementById("payment-status-badge");

      if (newStatus === "CANCEL") {
        if (cancelledNotice) cancelledNotice.style.display = "flex";
        if (timelineWrapper) timelineWrapper.style.display = "none";
      } else {
        if (cancelledNotice) cancelledNotice.style.display = "none";
        if (timelineWrapper) timelineWrapper.style.display = "block";
      }

      if (paymentBadge) {
        if (newStatus === "PAID") {
          paymentBadge.innerHTML = '<span class="badge badge-success" style="background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid #34d399; font-weight: 600; padding: 4px 10px; border-radius: 9999px; display: inline-flex; align-items: center; gap: 4px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Paid</span>';
        } else {
          paymentBadge.innerHTML = '<span class="badge badge-outline" style="background: rgba(242, 202, 80, 0.1); color: var(--rdh-primary); border: 1px solid var(--rdh-outline-variant); font-size: 0.75rem; padding: 4px 10px; border-radius: 9999px; display: inline-flex; align-items: center; gap: 4px;"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> Payment: COD</span>';
        }
      }

      var currentIndex = newStatus === "PAID" ? STEPS.length : STEPS.indexOf(newStatus);
      if (currentIndex === -1) currentIndex = 0;

      for (var i = 0; i < STEPS.length; i++) {
        var code = STEPS[i];
        var stepEl = document.getElementById("step-" + code);
        var nodeEl = document.getElementById("step-node-" + code);
        var lineEl = document.getElementById("line-" + code);

        if (!stepEl || !nodeEl) continue;

        stepEl.classList.remove("completed", "active", "upcoming");

        if (i < currentIndex) {
          stepEl.classList.add("completed");
          nodeEl.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
          if (lineEl) lineEl.classList.add("completed");
        } else if (i === currentIndex) {
          stepEl.classList.add("active");
          nodeEl.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>';
          if (lineEl) lineEl.classList.remove("completed");
        } else {
          stepEl.classList.add("upcoming");
          nodeEl.textContent = (i + 1).toString();
          if (lineEl) lineEl.classList.remove("completed");
        }
      }
    }

    function updateStatusDisplay(newStatus) {
      status = newStatus;
      if (statusDisplay) {
        statusDisplay.textContent = labels[status] || status;
      }
      updateTimeline(status);
    }


    function setConnected(isConnected) {
      if (offlineWarning) {
        offlineWarning.style.display = isConnected ? "none" : "block";
      }
    }

    // Set initial state
    setConnected(false);

    var chatForm = document.getElementById("chat-form");
    if (chatForm) {
      chatForm.addEventListener("htmx:afterRequest", function(event) {
        if (event.detail.successful) {
          chatForm.reset();
        }
      });
    }

    var scheme = window.location.protocol === "https:" ? "wss" : "ws";
    var url = scheme + "://" + window.location.host + "/ws/orders/" + orderId + "/";
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
        socket = new WebSocket(url);
      } catch (err) {
        scheduleReconnect();
        return;
      }

      socket.onopen = function() {
        setConnected(true);
        if (wasDisconnected) {
          syncStatusOnReconnect();
        }
        attempts = 0;
        currentDelay = initialDelay;
        wasDisconnected = false;
      };

      socket.onclose = function() {
        setConnected(false);
        wasDisconnected = true;
        scheduleReconnect();
      };

      socket.onerror = function() {
        // socket.onclose fires after onerror
      };

      socket.onmessage = function(event) {
        var data = JSON.parse(event.data);
        if (data.type === "order.status" && data.status) {
          updateStatusDisplay(data.status);
        } else if (data.type === "order.message") {
          appendMessage(data);
        }
      };
    }

    function scheduleReconnect() {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }

      if (attempts >= maxAttempts) {
        console.log("Max reconnect attempts reached for order tracker.");
        if (offlineWarning) {
          offlineWarning.innerHTML = 'Live updates disconnected. <a href="javascript:location.reload()" style="color: inherit; text-decoration: underline; font-weight: bold;">Refresh page</a> for current status.';
          offlineWarning.style.display = "block";
        }
        return;
      }

      attempts++;
      var wait = currentDelay;
      currentDelay = Math.min(currentDelay * 2, maxDelay);

      reconnectTimer = setTimeout(function() {
        connect();
      }, wait);
    }

    function syncStatusOnReconnect() {
      fetch(window.location.href, {
        headers: { "X-Requested-With": "XMLHttpRequest" }
      })
        .then(function(res) { return res.text(); })
        .then(function(html) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(html, "text/html");
          var newContainer = doc.getElementById("order-tracker-container");
          if (newContainer) {
            var latestStatus = newContainer.getAttribute("data-initial-status");
            if (latestStatus && latestStatus !== status) {
              updateStatusDisplay(latestStatus);
            }
          }
        })
        .catch(function() { /* best-effort sync */ });
    }

    connect();

    function appendMessage(data) {
      var thread = document.getElementById("message-thread");
      if (!thread || document.getElementById("msg-" + data.message_id)) return;
      var li = document.createElement("li");
      li.id = "msg-" + data.message_id;
      li.className = "msg";
      li.textContent = data.body;
      thread.appendChild(li);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initOrderTracker);
  } else {
    initOrderTracker();
  }
})();
