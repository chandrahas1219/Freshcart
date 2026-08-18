# **FreshCart AI Chat Assistant - Setup & Usage Guide**

## **Overview**

The AI Chat Assistant uses **Mistral API** to understand customer prompts and automatically perform grocery ordering, profile updates, and account management tasks.

---

## **What It Does**

### ✅ **Supported Actions**

#### **1. Add Items to Cart**
```
User: "Add 2kg tomato and 1 onion to cart"
AI: Shows preview → User confirms → Items added to cart
```

#### **2. View Cart**
```
User: "What's in my cart?"
AI: Shows current cart contents with total price
```

#### **3. Browse Inventory**
```
User: "Show me all vegetables"
AI: Lists all items with prices and stock status
```

#### **4. View Order History** (Auto-executed)
```
User: "Show my last orders"
AI: Displays last 5 orders with dates and totals
```

#### **5. Manage Cart**
```
User: "Remove tomato from cart"
AI: Shows preview → User confirms → Item removed
User: "Clear my cart"
AI: Shows confirmation → User confirms → Cart cleared
```

#### **6. Update Profile**
```
User: "Change my phone to 9876543210"
AI: Shows current → new values → User confirms → Redirects to profile page
```

#### **7. Checkout**
```
User: "Take me to checkout"
AI: Shows total → User confirms → Redirects to payment page
```

#### **8. Send Receipt** (Auto-executed)
```
User: "Send my receipt"
AI: Automatically sends latest receipt to email
```

#### **9. Out of Scope Handling**
```
User: "What's the weather?"
AI: "Sorry, I only help with grocery orders. Browse items?"
```

---

## **Prerequisites**

1. ✅ **Brevo Account** (for API key)
   - Already set up if you configured email

2. ✅ **Environment Variables** (already in Render)
   - `BREVO_API_KEY` - Mistral API key
   - `FLASK_SECRET_KEY` - Already configured
   - `GOOGLE_SHEETS_CREDENTIALS` - Already configured

---

## **How to Activate (For Users)**

### **Step 1: Log in as Customer**
- Go to app → Click "Shop login"
- Enter email/password

### **Step 2: Look for Chat Button**
- **Bottom right** corner of screen
- **💬** emoji button (floating)
- Click to open chat modal

### **Step 3: Start Chatting**
- Type your request
- Click send (→ button)
- AI responds with preview (if needed)
- **Confirm** or **Cancel**
- Done! ✅

---

## **Example Conversations**

### **Scenario 1: Quick Order**
```
You:  "Add 2kg tomato and 1 carrot"
AI:   "Ready to add:
       • Tomato: 2kg = ₹160
       • Carrot: 1kg = ₹50
       Total: ₹210
       [Confirm] [Cancel]"
You:  Click [Confirm]
AI:   "✅ Added to cart! [Go to Checkout] [Keep Shopping]"
```

### **Scenario 2: View History**
```
You:  "Show my orders"
AI:   "Your orders (3 total):
       Order #1: 2026-08-14 - 5 items - ₹450
       Order #2: 2026-08-13 - 3 items - ₹280
       [View Full History] [Place New Order]"
```

### **Scenario 3: Profile Update**
```
You:  "Update my phone to 9999999999"
AI:   "Update profile:
       Field: phone
       Current: 9876543210
       New: 9999999999
       [Confirm] [Cancel]"
You:  Click [Confirm]
AI:   "✅ Phone updated! [Redirecting to profile page...]"
```

### **Scenario 4: Invalid Request**
```
You:  "Add 100kg tomato"
AI:   "⚠️ We only have 50kg tomato in stock (not 100kg).
       [Add 50kg] [Cancel] [View Alternatives]"
```

### **Scenario 5: Out of Scope**
```
You:  "What's the capital of India?"
AI:   "Sorry, I only help with grocery orders!
       Can I help you:
       [Browse Items] [View Cart] [Order History]?"
```

---

## **AI Classification Logic**

The AI uses **Mistral** to classify prompts into **12 action types**:

| Action | Requires Confirmation | Auto-Redirect |
|--------|----------------------|----------------|
| add_to_cart | ✅ Yes | ✅ To checkout |
| view_cart | ❌ No | View only |
| view_inventory | ❌ No | View only |
| view_order_history | ❌ No | View only |
| view_profile | ❌ No | View only |
| update_profile | ✅ Yes | ✅ To profile |
| clear_cart | ✅ Yes | ✅ To shop |
| remove_from_cart | ✅ Yes | ✅ To cart |
| checkout | ✅ Yes | ✅ To payment |
| send_receipt | ❌ No (Auto) | Email only |
| out_of_scope | ❌ No | None |
| not_feasible | ❌ No | Suggest alt |

---

## **Error Handling**

### **"Chat is not available"**
- Mistral API key is not configured
- **Fix:** Add `BREVO_API_KEY` to Render environment

### **"Please log in to use chat"**
- User is not logged in to customer portal
- **Fix:** Log in first

### **"Connection error"**
- Mistral API is down or unreachable
- **Fix:** Try again in a few moments

### **"Item not found"**
- User asked for item not in inventory
- **AI Response:** "We don't have X. Try: Y instead?"

---

## **Architecture**

```
┌─ Frontend (chat.js)
│  ├─ User types message
│  ├─ Send to /api/chat/message
│  └─ Show response/preview
│
├─ Backend (chat_routes.py)
│  ├─ Receive prompt
│  ├─ Call AI classifier
│  └─ Route to handler
│
├─ AI Classifier (ai_chat_handler.py)
│  ├─ Mistral API call
│  ├─ Extract action type
│  ├─ Validate feasibility
│  └─ Return structured response
│
└─ Action Execution
   ├─ Validate (stock, permissions)
   ├─ Show preview
   ├─ Wait for user confirm
   └─ Execute action
```

---

## **Files Involved**

| File | Purpose |
|------|---------|
| `ai_chat_handler.py` | Core AI logic & action routing |
| `routes/chat_routes.py` | Flask API endpoints |
| `templates/chat_popup.html` | Chat UI modal |
| `static/js/chat.js` | Frontend interactivity |
| `app.py` | Register chat blueprint |
| `requirements.txt` | Add `requests` library |

---

## **Customization**

### **Change Chat Button Icon**
In `templates/chat_popup.html`, change:
```html
<button id="chat-toggle" class="chat-toggle">
  💬  <!-- Change this emoji -->
</button>
```

### **Change Welcome Message**
In `templates/chat_popup.html`, update:
```html
<p>👋 Hi! I'm your grocery assistant. Try:</p>
<ul>
  <li>"Your custom example"</li>
</ul>
```

### **Change Colors**
In `templates/chat_popup.html`, modify CSS variables:
```css
/* Header gradient */
background: linear-gradient(135deg, #3b6e4f 0%, #2f5a41 100%);
/* Button colors */
background: #d2452a;
```

### **Add More Mistral Models**
In `ai_chat_handler.py`, change:
```python
MISTRAL_MODEL = "ministral-8b-2512"
# Options: mistral-tiny, mistral-small-latest, mistral-medium-latest, mistral-large-latest
```

---

## **Performance Tips**

1. **Response Time**: ~1-2 seconds (Mistral API call)
2. **Optimize**: Use smaller model for faster response
3. **Caching**: Not implemented yet (could cache frequent queries)

---

## **Future Enhancements**

- [ ] **Voice input** - Speak instead of type
- [ ] **Smart reordering** - "Reorder my last cart"
- [ ] **Recommendations** - "Suggest items for me"
- [ ] **Subscription orders** - "Subscribe weekly"
- [ ] **Multi-language** - Support Hindi, Tamil, etc.
- [ ] **Conversation memory** - Remember previous context
- [ ] **Admin chat** - For store managers

---

## **Troubleshooting**

### **Chat button not showing**
- ❌ You're not logged in (customer portal only)
- ❌ You're viewing admin page
- ✅ **Fix:** Log in as customer first

### **API Key error**
- ❌ `BREVO_API_KEY` not set in Render
- ✅ **Fix:** Go to Render → Environment → Add/update key

### **Mistral returns invalid JSON**
- ❌ API response is malformed
- ✅ **Fix:** Restart Render app, try again

### **Chat hangs on loading**
- ❌ Network issue or timeout
- ✅ **Fix:** Refresh page, check connection

---

## **Testing Checklist**

- [ ] Chat button appears (bottom right)
- [ ] Can type and send messages
- [ ] "Add to cart" shows preview
- [ ] "View history" shows orders
- [ ] "Out of scope" handling works
- [ ] Confirmation flow works
- [ ] Redirect to checkout works
- [ ] Error messages are clear
- [ ] Mobile responsive
- [ ] Works on phone browser

---

## **Support**

If chat isn't working:

1. Check Render logs: Go to project → **Logs** tab
2. Look for error messages with "mistral" or "chat"
3. Verify `BREVO_API_KEY` is set correctly
4. Restart Render instance
5. Clear browser cache & try again

---

**Enjoy your AI-powered grocery shopping! 🚀**
