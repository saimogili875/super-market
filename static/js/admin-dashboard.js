/**
 * Admin Dashboard — live updates via WebSocket
 *
 * Connects to ws/dashboard/ (DashboardConsumer) and reacts to order.status
 * events by refreshing the affected order card via HTMX, or inserting a new
 * card for freshly placed orders.
 *
 * CSP-safe: loaded as an external file via {% static %} + defer, using
 * standard DOM event listeners (no eval or inline handlers).
 */
(function() {
  function initAdminDashboard() {
    var container = document.getElementById("admin-dashboard");
    if (!container) return;

    var connected = false;

    function connect() {
      var scheme = window.location.protocol === "https:" ? "wss" : "ws";
      var url = scheme + "://" + window.location.host + "/ws/dashboard/";
      var socket;

      try {
        socket = new WebSocket(url);
      } catch (err) {
        return; // Socket unavailable; server-rendered state stands.
      }

      socket.onopen = function () {
        connected = true;
      };

      socket.onclose = function () {
        connected = false;
        // Attempt reconnect after a short delay
        setTimeout(function () {
          connect();
        }, 3000);
      };

      socket.onmessage = function (event) {
        var data = JSON.parse(event.data);
        if (data.type === "order.status") {
          handleStatusEvent(data);
        }
      };
    }

    function handleStatusEvent(data) {
      var orderId = data.order_id;
      var status = data.status;
      var cardId = "order-card-" + orderId;
      var existing = document.getElementById(cardId);

      // Terminal statuses: remove the card after a brief highlight
      if (status === "PAID" || status === "CANCEL") {
        if (existing) {
          existing.style.opacity = "0.5";
          existing.style.transition = "opacity 0.5s ease";
          setTimeout(function () {
            existing.remove();
          }, 800);
        }
        showToast("Order #" + orderId + " → " + status);
        return;
      }

      // Existing card: refresh it via HTMX GET
      if (existing) {
        var cardUrl = getCardUrl(orderId);
        if (typeof htmx !== "undefined") {
          htmx.ajax("GET", cardUrl, {target: "#" + cardId, swap: "outerHTML"});
        }
        showToast("Order #" + orderId + " → " + status);
        return;
      }

      // New order (not on page yet): fetch and prepend
      if (status === "PLACED") {
        insertNewOrder(orderId);
        showToast("🆕 New order #" + orderId);
      }
    }

    function insertNewOrder(orderId) {
      var cardUrl = getCardUrl(orderId);

      // Fetch the card HTML and insert into the appropriate grid
      var tempId = "new-order-slot-" + orderId;
      var slot = document.createElement("div");
      slot.id = tempId;

      var deliveryGrid = document.getElementById("delivery-grid");
      var dineSection = document.getElementById("dine-in-section");

      if (deliveryGrid) {
        deliveryGrid.prepend(slot);
      } else if (dineSection) {
        var section = document.getElementById("delivery-section");
        if (section) {
          var empty = section.querySelector(".empty-state");
          if (empty) {
            var grid = document.createElement("div");
            grid.className = "order-grid";
            grid.id = "delivery-grid";
            empty.replaceWith(grid);
            grid.prepend(slot);
          }
        }
      }

      if (document.getElementById(tempId) && typeof htmx !== "undefined") {
        htmx.ajax("GET", cardUrl, {
          target: "#" + tempId,
          swap: "outerHTML",
        }).then(function () {
          var card = document.getElementById("order-card-" + orderId);
          if (card) {
            card.classList.add("card--new");
          }
        });
      }
    }

    function getCardUrl(orderId) {
      var path = window.location.pathname;
      var base = path.replace(/dashboard\/$/, "");
      return base + orderId + "/card/";
    }

    function showToast(message) {
      var region = document.getElementById("toast-region");
      if (!region) return;

      var toast = document.createElement("div");
      toast.className = "toast";
      toast.textContent = message;
      region.appendChild(toast);

      setTimeout(function () {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.3s ease";
        setTimeout(function () {
          toast.remove();
        }, 300);
      }, 3000);
    }

    connect();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAdminDashboard);
  } else {
    initAdminDashboard();
  }
})();
