"""
AI Chat Handler - Uses Mistral's native function-calling to understand the
user's request, decide which FreshCart feature (if any) it maps to, and
produce a warm, human-sounding reply alongside the structured action.

Design:
  - ONE call to Mistral per user message, using the `tools` API (not a
    hand-rolled "return JSON" prompt). We force a tool call
    (tool_choice="any") against a single tool, `resolve_customer_request`,
    whose parameters bundle:
      * reply                -> the natural-language, human-toned message
                                 the assistant says back to the user
      * action_type          -> which FreshCart functionality this maps to
                                 (or "smalltalk" / "out_of_scope" / "not_feasible")
      * extracted_items / extracted_profile_change -> structured arguments
        for that functionality
  - Mistral decides the intent AND writes the human reply in the same
    structured call, so we never have to reconcile two separate outputs.
  - All facts that must be accurate (prices, stock, totals, order history)
    are still computed deterministically in Python from Google Sheets data,
    never trusted from the model. The model's `reply` is just the
    conversational wrapper around those facts.
"""

import os
import json
from datetime import datetime
import requests

from mongo_helpers import (
    GROCERIES_FILE, CUSTOMERS_FILE,
    get_all_rows, get_row_by_id
)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
MISTRAL_MODEL = "ministral-8b-2512"

MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"

# All the things a FreshCart customer can actually do. Kept in one place so
# the system prompt and the routing table can't drift apart.
ACTION_TYPES = [
    "add_to_cart", "view_cart", "view_inventory", "view_order_history",
    "view_profile", "update_profile", "clear_cart", "remove_from_cart",
    "checkout", "send_receipt",
    "smalltalk",      # greetings, thanks, "who are you", chit-chat
    "out_of_scope",   # unrelated to FreshCart (weather, news, etc.)
    "not_feasible",   # a real FreshCart request that can't be satisfied
]

SYSTEM_PROMPT = """You are Sprout, the friendly in-app shopping assistant for \
FreshCart, a grocery ordering app. You talk like a helpful, warm human \
teammate would over chat - never like a robot reading back a form. Keep \
replies short (1-3 sentences), plain-spoken, and specific to what the \
person actually asked. Light, occasional emoji is fine; don't overdo it.

You have access to one tool, `resolve_customer_request`. For EVERY message \
the user sends, call that tool exactly once. Two things always come out of \
that call:

1. `reply` - what you'd actually say back to the person, in your own \
   words, acknowledging their request. This is shown to the user verbatim, \
   so make it sound like a person wrote it. Never put raw prices, stock \
   counts, or item lists in `reply` - the app fills those in separately \
   from real inventory data. Just talk about *what you're doing*, e.g. \
   "Sure, adding that now!" or "Here's what's in your cart." or "I can't \
   place an order for more onions than we actually have in stock, sorry!"
2. `action_type` - which FreshCart feature this maps to, chosen from:
   - add_to_cart, view_cart, view_inventory, view_order_history,
     view_profile, update_profile, clear_cart, remove_from_cart,
     checkout, send_receipt
   - smalltalk: greetings, thanks, "who are you", jokes, anything
     conversational with no FreshCart action attached
   - out_of_scope: unrelated to FreshCart entirely (weather, news, general
     trivia, coding help, etc.)
   - not_feasible: it's a real FreshCart request but can't be done as
     asked (e.g. asking for more of an item than is in stock, or an item
     that doesn't exist)

Use `feasibility` to say whether the request is "feasible",
"partially_feasible" (some items work, some don't), or "not_feasible".
Only set requires_confirmation=true for actions that change data
(add_to_cart, update_profile, clear_cart, remove_from_cart, checkout).
Viewing things and sending a receipt never need confirmation.

When the user names items, extract them into extracted_items with your
best-guess quantity and unit (default quantity 1 if unstated). When they
ask to change profile info, fill extracted_profile_change with the field
("name", "email", or "phone") and the new value.

Today's available inventory:
{inventory_text}
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "resolve_customer_request",
            "description": (
                "Classify the customer's chat message into a FreshCart "
                "action (or smalltalk / out_of_scope / not_feasible) and "
                "write the natural-language reply to show them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reply": {
                        "type": "string",
                        "description": (
                            "Warm, human, conversational reply shown "
                            "verbatim to the user. No raw prices/stock "
                            "numbers here - just natural conversation."
                        ),
                    },
                    "action_type": {
                        "type": "string",
                        "enum": ACTION_TYPES,
                    },
                    "feasibility": {
                        "type": "string",
                        "enum": ["feasible", "partially_feasible", "not_feasible"],
                    },
                    "requires_confirmation": {"type": "boolean"},
                    "extracted_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    },
                    "extracted_profile_change": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "enum": ["name", "email", "phone"]},
                            "value": {"type": "string"},
                        },
                    },
                    "alternatives": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "reason_if_not_feasible": {"type": "string"},
                },
                "required": ["reply", "action_type", "feasibility"],
            },
        },
    }
]


class ChatHandler:
    """Main handler for AI chat interactions"""

    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY environment variable not configured")

    def classify_prompt(self, user_prompt: str, customer_id: str = None, history: list = None) -> dict:
        """
        Use Mistral's function-calling to figure out what the user wants,
        AND get a human-toned reply, in a single request.

        `history` is this customer's recent turns (oldest first), each a
        dict like {"role": "user"|"assistant", "content": "..."}. It's
        passed straight into the messages array so the model has short-term
        conversational memory (e.g. "add 2 more of that").
        """

        groceries = get_all_rows(GROCERIES_FILE)
        inventory_text = "\n".join([
            f"- {g['Name']} ({g['Unit']}): stock {g['QuantityInStock']}"
            for g in groceries
        ])

        system_message = SYSTEM_PROMPT.format(inventory_text=inventory_text)

        history_messages = [
            {"role": h["role"], "content": h["content"]} for h in (history or [])
        ]

        try:
            response = requests.post(
                MISTRAL_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MISTRAL_MODEL,
                    "messages": [
                        {"role": "system", "content": system_message},
                        *history_messages,
                        {"role": "user", "content": user_prompt},
                    ],
                    "tools": TOOLS,
                    "tool_choice": "any",
                    "temperature": 0.4,
                },
                timeout=15
            )

            if response.status_code != 200:
                return {
                    "understood": False,
                    "error": f"Mistral API error: {response.status_code}",
                    "message": "Sorry, I couldn't process that. Try again?"
                }

            result = response.json()
            message = result["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                # Model answered in plain text instead of calling the tool -
                # still usable as a smalltalk-style reply.
                return {
                    "understood": True,
                    "reply": message.get("content", "").strip() or "Got it!",
                    "action_type": "smalltalk",
                    "feasibility": "feasible",
                    "requires_confirmation": False,
                }

            arguments = tool_calls[0]["function"]["arguments"]
            parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
            parsed["understood"] = True
            parsed.setdefault("reply", "Got it!")
            parsed.setdefault("action_type", "smalltalk")
            parsed.setdefault("feasibility", "feasible")
            parsed.setdefault("requires_confirmation", False)
            return parsed

        except json.JSONDecodeError:
            return {
                "understood": False,
                "error": "Failed to parse AI response",
                "message": "Sorry, I didn't understand. Try: 'Add tomato to cart' or 'Show my orders'"
            }
        except requests.RequestException as e:
            return {
                "understood": False,
                "error": f"API Error: {str(e)}",
                "message": "Connection error. Please try again."
            }

    def handle_action(self, parsed_prompt: dict, customer_id: str, cart: dict) -> dict:
        """
        Route the classified action to appropriate handler.
        Every handler blends the AI's human `reply` with the deterministic,
        data-accurate details (prices/stock/totals) it computes itself.
        """

        if not parsed_prompt.get("understood"):
            return {
                "success": False,
                "message": parsed_prompt.get("message", "Could not understand"),
                "action": None,
                "requires_confirmation": False
            }

        ai_reply = parsed_prompt.get("reply", "").strip()
        action_type = parsed_prompt.get("action_type", "out_of_scope")
        feasibility = parsed_prompt.get("feasibility", "not_feasible")

        # Validate feasibility first
        if feasibility == "not_feasible":
            return self._handle_not_feasible(parsed_prompt, ai_reply)

        if feasibility == "partially_feasible":
            return self._handle_partially_feasible(parsed_prompt, ai_reply)

        # Route to action handlers
        handlers = {
            "add_to_cart": lambda: self._handle_add_to_cart(parsed_prompt, customer_id, cart, ai_reply),
            "view_cart": lambda: self._handle_view_cart(cart, ai_reply),
            "view_inventory": lambda: self._handle_view_inventory(ai_reply),
            "view_order_history": lambda: self._handle_view_order_history(customer_id, ai_reply),
            "view_profile": lambda: self._handle_view_profile(customer_id, ai_reply),
            "update_profile": lambda: self._handle_update_profile(parsed_prompt, customer_id, ai_reply),
            "clear_cart": lambda: self._handle_clear_cart(cart, ai_reply),
            "remove_from_cart": lambda: self._handle_remove_from_cart(parsed_prompt, cart, ai_reply),
            "checkout": lambda: self._handle_checkout(cart, ai_reply),
            "send_receipt": lambda: self._handle_send_receipt(customer_id, ai_reply),
            "smalltalk": lambda: self._handle_smalltalk(ai_reply),
            "out_of_scope": lambda: self._handle_out_of_scope(ai_reply),
        }

        handler = handlers.get(action_type, lambda: self._handle_out_of_scope(ai_reply))
        return handler()

    @staticmethod
    def _compose(ai_reply: str, details: str = "") -> str:
        """Blend the model's human reply with deterministic, factual details."""
        ai_reply = (ai_reply or "").strip()
        details = (details or "").strip()
        if ai_reply and details:
            return f"{ai_reply}\n\n{details}"
        return ai_reply or details

    def _handle_smalltalk(self, ai_reply: str) -> dict:
        """Pure conversation - no FreshCart action, just the human reply."""
        return {
            "success": True,
            "message": ai_reply or "Hey! How can I help you shop today?",
            "action": None,
            "requires_confirmation": False,
        }

    def _handle_add_to_cart(self, prompt: dict, customer_id: str, cart: dict, ai_reply: str) -> dict:
        """Add items to cart with validation"""
        items = prompt.get("extracted_items", [])
        if not items:
            return {
                "success": False,
                "message": self._compose(ai_reply, "I didn't catch which item(s) you meant."),
                "action": None
            }

        # Validate all items exist and have stock
        invalid_items = []
        preview_items = []
        total_price = 0

        for item in items:
            grocery = self._find_item(item["name"])
            if not grocery:
                invalid_items.append(f"{item['name']} (not in inventory)")
                continue

            available = int(grocery["QuantityInStock"])
            requested = item.get("quantity", 1)

            if requested > available:
                invalid_items.append(
                    f"{item['name']}: requested {requested}{item.get('unit', 'units')}, "
                    f"only {available} available"
                )
                continue

            price = float(grocery["PricePerUnit"]) * requested
            total_price += price
            preview_items.append({
                "name": grocery["Name"],
                "quantity": requested,
                "unit": grocery.get("Unit", "units"),
                "price": float(grocery["PricePerUnit"]),
                "subtotal": price
            })

        if not preview_items and invalid_items:
            return {
                "success": False,
                "message": self._compose(ai_reply, f"⚠️ {', '.join(invalid_items)}"),
                "action": None,
                "requires_confirmation": False,
                "alternatives": ["Try a different quantity or item"]
            }

        # Build deterministic itemized details
        details = "Ready to add:\n\n"
        for item in preview_items:
            details += f"• {item['name']}: {item['quantity']}{item['unit']} = ₹{item['subtotal']:.2f}\n"
        details += f"\nTotal: ₹{total_price:.2f}"

        if invalid_items:
            details += f"\n\n⚠️ Note: {', '.join(invalid_items)}"

        return {
            "success": True,
            "message": self._compose(ai_reply, details),
            "action": "add_to_cart",
            "requires_confirmation": True,
            "preview": {
                "items": preview_items,
                "total": total_price,
                "invalid_items": invalid_items
            },
            "redirect_to": "/customer/checkout"
        }

    def _handle_view_cart(self, cart: dict, ai_reply: str) -> dict:
        """Show current cart contents"""
        if not cart:
            return {
                "success": True,
                "message": self._compose(ai_reply, "Your cart is empty. Start shopping? [View Items]"),
                "action": "view_cart",
                "requires_confirmation": False,
                "redirect_to": "/customer/dashboard"
            }

        items = []
        total = 0
        for item_id, qty in cart.items():
            grocery = get_row_by_id(GROCERIES_FILE, "ItemID", item_id)
            if grocery:
                price = float(grocery["PricePerUnit"]) * qty
                total += price
                items.append({
                    "name": grocery["Name"],
                    "quantity": qty,
                    "unit": grocery.get("Unit", "units"),
                    "price": float(grocery["PricePerUnit"]),
                    "subtotal": price
                })

        details = f"Your cart ({len(items)} items):\n\n"
        for item in items:
            details += f"• {item['name']}: {item['quantity']}{item['unit']} = ₹{item['subtotal']:.2f}\n"
        details += f"\nTotal: ₹{total:.2f}\n\n[Checkout] [Keep Shopping]"

        return {
            "success": True,
            "message": self._compose(ai_reply, details),
            "action": "view_cart",
            "requires_confirmation": False,
            "preview": {"items": items, "total": total},
            "redirect_to": "/customer/cart"
        }

    def _handle_view_inventory(self, ai_reply: str) -> dict:
        """List all available items"""
        groceries = get_all_rows(GROCERIES_FILE)

        by_category = {}
        for g in groceries:
            cat = g.get("Category", "Other")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(g)

        details = "Available items:\n\n"
        for category, items in by_category.items():
            details += f"📦 {category.upper()}\n"
            for item in items:
                stock = int(item["QuantityInStock"])
                status = "✅" if stock > 0 else "❌"
                details += f"  {status} {item['Name']}: ₹{item['PricePerUnit']}/{item.get('Unit', 'unit')} (Stock: {stock})\n"
            details += "\n"

        details += "[Add Items] [View Cart]"

        return {
            "success": True,
            "message": self._compose(ai_reply, details),
            "action": "view_inventory",
            "requires_confirmation": False,
            "redirect_to": "/customer/dashboard"
        }

    def _handle_view_order_history(self, customer_id: str, ai_reply: str) -> dict:
        """Fetch and display order history"""
        from mongo_helpers import parse_transaction_history

        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Could not find customer"),
                "action": None
            }

        orders = parse_transaction_history(customer.get("TransactionHistory", "[]"))
        if not orders:
            return {
                "success": True,
                "message": self._compose(ai_reply, "No orders yet. Start shopping! [Browse Items]"),
                "action": "view_order_history",
                "requires_confirmation": False,
                "redirect_to": "/customer/dashboard"
            }

        details = f"Your orders ({len(orders)} total):\n\n"
        for order in reversed(orders[-5:]):  # Last 5 orders
            details += f"Order #{order.get('order_id', 'N/A')}: {order.get('timestamp', 'N/A')}\n"
            details += f"  Items: {len(order.get('line_items', []))}\n"
            details += f"  Total: ₹{order.get('total', 0):.2f}\n"
            details += f"  Payment: {order.get('payment_method', 'Unknown')}\n\n"

        details += "[View Full History] [Place New Order]"

        return {
            "success": True,
            "message": self._compose(ai_reply, details),
            "action": "view_order_history",
            "requires_confirmation": False,
            "redirect_to": "/customer/history"
        }

    def _handle_view_profile(self, customer_id: str, ai_reply: str) -> dict:
        """Show user profile"""
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Could not find profile"),
                "action": None
            }

        details = "Your profile:\n\n"
        details += f"Name: {customer.get('Name', 'N/A')}\n"
        details += f"Email: {customer.get('Email', 'N/A')}\n"
        details += f"Phone: {customer.get('Phone', 'N/A')}\n\n"
        details += "[Edit Profile] [Change Password]"

        return {
            "success": True,
            "message": self._compose(ai_reply, details),
            "action": "view_profile",
            "requires_confirmation": False,
            "redirect_to": "/customer/profile"
        }

    def _handle_update_profile(self, prompt: dict, customer_id: str, ai_reply: str) -> dict:
        """Update profile (show preview, require confirmation)"""
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Could not find profile"),
                "action": None
            }

        change = prompt.get("extracted_profile_change", {})
        field = change.get("field", "")
        new_value = change.get("value", "")

        if not field or not new_value:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Could not understand what to change. Try: 'Update my phone to 9876543210'"),
                "action": None
            }

        current_value = customer.get(field.capitalize() if field == "phone" else field, "N/A")

        details = f"Update profile:\n\n"
        details += f"Field: {field}\n"
        details += f"Current: {current_value}\n"
        details += f"New: {new_value}\n\n"
        details += "⚠️ For security, confirm this change on the profile page."

        return {
            "success": True,
            "message": self._compose(ai_reply, details),
            "action": "update_profile",
            "requires_confirmation": True,
            "preview": {
                "field": field,
                "current": current_value,
                "new": new_value
            },
            "redirect_to": "/customer/profile"
        }

    def _handle_clear_cart(self, cart: dict, ai_reply: str) -> dict:
        """Clear entire cart"""
        if not cart:
            return {
                "success": True,
                "message": self._compose(ai_reply, "Cart is already empty"),
                "action": None
            }

        return {
            "success": True,
            "message": self._compose(ai_reply, f"Clear cart? This will remove {len(cart)} items."),
            "action": "clear_cart",
            "requires_confirmation": True,
            "preview": {"items_to_remove": len(cart)},
            "redirect_to": "/customer/dashboard"
        }

    def _handle_remove_from_cart(self, prompt: dict, cart: dict, ai_reply: str) -> dict:
        """Remove specific item from cart"""
        items = prompt.get("extracted_items", [])
        if not items:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Which item to remove?"),
                "action": None
            }

        item_name = items[0]["name"]
        grocery = self._find_item(item_name)

        if not grocery:
            return {
                "success": False,
                "message": self._compose(ai_reply, f"Item '{item_name}' not found"),
                "action": None
            }

        item_id = str(grocery["ItemID"])
        if item_id not in cart:
            return {
                "success": False,
                "message": self._compose(ai_reply, f"{item_name} is not in your cart"),
                "action": None
            }

        return {
            "success": True,
            "message": self._compose(ai_reply, f"Remove {item_name} from cart?"),
            "action": "remove_from_cart",
            "requires_confirmation": True,
            "preview": {"item_id": item_id, "item_name": item_name},
            "redirect_to": "/customer/cart"
        }

    def _handle_checkout(self, cart: dict, ai_reply: str) -> dict:
        """Proceed to checkout"""
        if not cart:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Your cart is empty. Add items first!"),
                "action": None
            }

        total = 0
        for item_id, qty in cart.items():
            grocery = get_row_by_id(GROCERIES_FILE, "ItemID", item_id)
            if grocery:
                total += float(grocery["PricePerUnit"]) * qty

        return {
            "success": True,
            "message": self._compose(ai_reply, f"Proceed to checkout? Total: ₹{total:.2f}"),
            "action": "checkout",
            "requires_confirmation": True,
            "preview": {"total": total, "items": len(cart)},
            "redirect_to": "/customer/checkout"
        }

    def _handle_send_receipt(self, customer_id: str, ai_reply: str) -> dict:
        """Auto-send receipt (no confirmation needed)"""
        from mongo_helpers import parse_transaction_history

        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": self._compose(ai_reply, "Could not find customer"),
                "action": None
            }

        orders = parse_transaction_history(customer.get("TransactionHistory", "[]"))
        if not orders:
            return {
                "success": False,
                "message": self._compose(ai_reply, "No orders to send receipt for"),
                "action": None
            }

        # Get latest order
        latest = orders[-1]
        return {
            "success": True,
            "message": self._compose(
                ai_reply,
                f"Sending receipt for Order #{latest.get('order_id')} to {customer.get('Email')}..."
            ),
            "action": "send_receipt",
            "requires_confirmation": False,
            "auto_execute": True,
            "preview": {"order_id": latest.get("order_id"), "total": latest.get("total")}
        }

    def _handle_out_of_scope(self, ai_reply: str) -> dict:
        """Handle out of scope queries - trust the model's own human phrasing"""
        return {
            "success": True,
            "message": ai_reply or "Sorry, I only help with FreshCart grocery orders! Can I help you shop instead?",
            "action": "out_of_scope",
            "requires_confirmation": False,
            "redirect_to": "/customer/dashboard"
        }

    def _handle_not_feasible(self, prompt: dict, ai_reply: str) -> dict:
        """Handle feasible but not possible requests"""
        reason = prompt.get("reason_if_not_feasible", "")
        alternatives = prompt.get("alternatives", [])

        details = ""
        if reason:
            details += f"⚠️ {reason}\n\n"
        if alternatives:
            details += "Alternatives:\n"
            for alt in alternatives[:3]:
                details += f"• {alt}\n"

        return {
            "success": True,
            "message": self._compose(ai_reply, details.strip()),
            "action": None,
            "requires_confirmation": False
        }

    def _handle_partially_feasible(self, prompt: dict, ai_reply: str) -> dict:
        """Handle requests where only part of it can be done - route through
        the normal action handler so the feasible part still goes through,
        while the reply/alternatives explain what couldn't be done."""
        action_type = prompt.get("action_type", "out_of_scope")
        if action_type == "add_to_cart":
            return self._handle_add_to_cart(prompt, None, {}, ai_reply)
        return self._handle_not_feasible(prompt, ai_reply)

    def _find_item(self, item_name: str) -> dict:
        """Search for item by name (case-insensitive, fuzzy match)"""
        groceries = get_all_rows(GROCERIES_FILE)
        name_lower = item_name.lower().strip()

        # Exact match first
        for g in groceries:
            if g["Name"].lower() == name_lower:
                return g

        # Partial match
        for g in groceries:
            if name_lower in g["Name"].lower():
                return g

        return None
