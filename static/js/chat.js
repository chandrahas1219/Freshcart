/**
 * FreshCart AI Chat - Frontend Handler
 * Manages chat UI, message sending, and action confirmation
 */

class FreshCartChat {
  constructor() {
    this.modal = document.getElementById("chat-modal");
    this.toggle = document.getElementById("chat-toggle");
    this.closeBtn = document.getElementById("close-chat");
    this.form = document.getElementById("chat-form");
    this.input = document.getElementById("chat-input");
    this.messagesContainer = document.getElementById("chat-messages");
    this.pendingAction = document.getElementById("pending-action");
    this.actionPreview = document.getElementById("action-preview");
    this.confirmBtn = document.getElementById("confirm-btn");
    this.cancelBtn = document.getElementById("cancel-btn");

    this.currentAction = null;
    this.isLoading = false;

    this.init();
  }

  init() {
    // Event listeners
    this.toggle.addEventListener("click", () => this.toggleModal());
    this.closeBtn.addEventListener("click", () => this.toggleModal());
    this.form.addEventListener("submit", (e) => this.handleSubmit(e));
    this.confirmBtn.addEventListener("click", () => this.confirmAction());
    this.cancelBtn.addEventListener("click", () => this.cancelAction());

    // Close modal on outside click
    this.modal.addEventListener("click", (e) => {
      if (e.target === this.modal) {
        this.toggleModal();
      }
    });

    // Auto-focus input when modal opens
    const observer = new MutationObserver(() => {
      if (!this.modal.classList.contains("hidden")) {
        this.input.focus();
      }
    });
    observer.observe(this.modal, { attributes: true });
  }

  toggleModal() {
    this.modal.classList.toggle("hidden");
    if (!this.modal.classList.contains("hidden")) {
      this.input.focus();
    }
  }

  async handleSubmit(e) {
    e.preventDefault();

    const message = this.input.value.trim();
    if (!message || this.isLoading) return;

    // Clear input
    this.input.value = "";

    // Add user message to UI
    this.addMessage(message, "user");

    // Show loading indicator
    this.showLoading();
    this.isLoading = true;

    try {
      // Send to backend
      const response = await fetch("/api/chat/message", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          prompt: message,
          action: null
        })
      });

      const data = await response.json();

      // Remove loading indicator
      this.removeLoading();

      if (!response.ok) {
        if (response.status === 401) {
          this.addMessage("Please log in to use chat", "error");
          setTimeout(() => {
            window.location.href = "/customer/login";
          }, 1500);
          return;
        }
        this.addMessage(data.message || "An error occurred", "error");
        return;
      }

      // Show assistant response
      this.addMessage(data.message, "assistant");

      // Handle different response types
      if (data.requires_confirmation) {
        // Show action preview and confirmation buttons
        this.showPendingAction(data);
      } else if (data.redirect_to && data.auto_execute) {
        // Auto-redirect to page
        setTimeout(() => {
          window.location.href = data.redirect_to;
        }, 1500);
      } else if (data.redirect_to) {
        // Show redirect button in message
        this.addActionButton(data.redirect_to, "Continue");
      }

    } catch (error) {
      this.removeLoading();
      this.addMessage("Connection error. Please try again.", "error");
      console.error("Chat error:", error);
    }

    this.isLoading = false;
  }

  addMessage(text, type = "assistant") {
    const messageEl = document.createElement("div");
    messageEl.className = `chat-message ${type}`;

    const p = document.createElement("p");
    p.textContent = text;
    messageEl.appendChild(p);

    this.messagesContainer.appendChild(messageEl);
    this.scrollToBottom();
  }

  showLoading() {
    const messageEl = document.createElement("div");
    messageEl.className = "chat-message assistant";
    messageEl.id = "loading-message";

    const loadingDiv = document.createElement("div");
    loadingDiv.className = "chat-loading";
    loadingDiv.innerHTML = "<span></span><span></span><span></span>";

    messageEl.appendChild(loadingDiv);
    this.messagesContainer.appendChild(messageEl);
    this.scrollToBottom();
  }

  removeLoading() {
    const loading = document.getElementById("loading-message");
    if (loading) loading.remove();
  }

  showPendingAction(data) {
    this.currentAction = data;

    // Build preview text
    let preview = "";
    if (data.preview) {
      if (data.preview.items && Array.isArray(data.preview.items)) {
        preview += "Items:\n";
        data.preview.items.forEach((item) => {
          preview += `• ${item.name}: ${item.quantity}${item.unit || ""}\n`;
        });
      }
      if (data.preview.total) {
        preview += `\nTotal: ₹${data.preview.total.toFixed(2)}`;
      }
      if (data.preview.field) {
        preview += `Field: ${data.preview.field}\nNew: ${data.preview.new}`;
      }
    }

    this.actionPreview.textContent = preview || data.message;
    this.pendingAction.classList.remove("hidden");
  }

  async confirmAction() {
    if (!this.currentAction) return;

    this.confirmBtn.disabled = true;
    this.cancelBtn.disabled = true;

    try {
      const response = await fetch("/api/chat/confirm", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          action: this.currentAction.action,
          preview: this.currentAction.preview || {}
        })
      });

      const data = await response.json();

      if (data.success) {
        this.addMessage(data.message, "assistant");

        if (data.redirect_to) {
          setTimeout(() => {
            window.location.href = data.redirect_to;
          }, 1000);
        }
      } else {
        this.addMessage(data.message || "Action failed", "error");
      }

    } catch (error) {
      this.addMessage("Error confirming action", "error");
      console.error("Confirm error:", error);
    } finally {
      this.closePendingAction();
      this.confirmBtn.disabled = false;
      this.cancelBtn.disabled = false;
    }
  }

  cancelAction() {
    this.closePendingAction();
    this.addMessage("Action cancelled", "assistant");
  }

  closePendingAction() {
    this.pendingAction.classList.add("hidden");
    this.currentAction = null;
  }

  addActionButton(href, text) {
    const messageEl = document.createElement("div");
    messageEl.className = "chat-message assistant";

    const button = document.createElement("a");
    button.href = href;
    button.className = "btn btn-primary";
    button.style.marginTop = "0.5rem";
    button.style.textDecoration = "none";
    button.style.display = "inline-block";
    button.textContent = text;

    messageEl.appendChild(button);
    this.messagesContainer.appendChild(messageEl);
    this.scrollToBottom();
  }

  scrollToBottom() {
    setTimeout(() => {
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }, 0);
  }
}

// Initialize chat when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  // Only initialize if user is logged in (check for customer portal)
  if (window.location.pathname.includes("/customer")) {
    window.freshcartChat = new FreshCartChat();
  }
});
