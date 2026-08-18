"""
AI Chat Handler - Uses Mistral API to classify user prompts and route actions
"""

import os
import json
import re
from datetime import datetime
import requests

from google_sheets_helpers import (
    GROCERIES_FILE, CUSTOMERS_FILE,
    get_all_rows, get_row_by_id
)

MISTRAL_API_KEY = os.environ.get("BREVO_API_KEY")  # Reuse from Brevo
MISTRAL_MODEL = "mistral-small-latest"


class ChatHandler:
    """Main handler for AI chat interactions"""

    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        if not self.api_key:
            raise ValueError("BREVO_API_KEY (Mistral API) not configured")

    def classify_prompt(self, user_prompt: str, customer_id: str = None) -> dict:
        """
        Use Mistral to classify the user's prompt into action categories
        Returns a structured response with action type and parameters
        """
        
        # Build context about inventory
        groceries = get_all_rows(GROCERIES_FILE)
        inventory_text = "\n".join([
            f"- {g['Name']} ({g['Unit']}): ₹{g['PricePerUnit']}, Stock: {g['QuantityInStock']}"
            for g in groceries
        ])

        prompt = f"""You are an AI assistant for FreshCart, a grocery ordering app. 
Analyze this user prompt and classify it into one of these categories:

CATEGORIES:
1. "add_to_cart" - User wants to add items to cart. Extract item names and quantities.
2. "view_cart" - User wants to see current cart contents.
3. "view_inventory" - User wants to see available items.
4. "view_order_history" - User wants to see past orders.
5. "view_profile" - User wants to see their profile details.
6. "update_profile" - User wants to change name/phone/email.
7. "clear_cart" - User wants to empty the cart.
8. "remove_from_cart" - User wants to remove specific items.
9. "checkout" - User wants to proceed to payment.
10. "send_receipt" - User wants an order receipt.
11. "out_of_scope" - Unrelated query (weather, news, etc).
12. "not_feasible" - Related but impossible (ordering more stock than available).

AVAILABLE ITEMS:
{inventory_text}

USER PROMPT: "{user_prompt}"

RESPOND WITH ONLY A JSON OBJECT (no markdown, no extra text):
{{
  "action_type": "one of the categories above",
  "feasibility": "feasible" | "partially_feasible" | "not_feasible",
  "requires_confirmation": true | false,
  "confidence": 0.0 to 1.0,
  "extracted_items": [
    {{"name": "item_name", "quantity": 2, "unit": "kg"}}
  ],
  "extracted_profile_change": {{"field": "phone", "value": "9876543210"}},
  "message": "User-friendly response message",
  "alternatives": ["alternative 1", "alternative 2"],
  "reason_if_not_feasible": "explanation of why it's not possible",
  "error": null | "error message if parsing failed"
}}"""

        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MISTRAL_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3  # Low temperature for deterministic classification
                },
                timeout=10
            )

            if response.status_code != 200:
                return {
                    "understood": False,
                    "error": f"Mistral API error: {response.status_code}",
                    "message": "Sorry, I couldn't process that. Try again?"
                }

            result = response.json()
            response_text = result["choices"][0]["message"]["content"]
            
            # Clean up response (remove markdown if present)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()

            parsed = json.loads(response_text)
            parsed["understood"] = True
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
        Route the classified action to appropriate handler
        Returns response with preview/confirmation needed
        """

        if not parsed_prompt.get("understood"):
            return {
                "success": False,
                "message": parsed_prompt.get("message", "Could not understand"),
                "action": None,
                "requires_confirmation": False
            }

        action_type = parsed_prompt.get("action_type", "out_of_scope")
        feasibility = parsed_prompt.get("feasibility", "not_feasible")

        # Validate feasibility first
        if feasibility == "not_feasible":
            return self._handle_not_feasible(parsed_prompt)

        if feasibility == "partially_feasible":
            return self._handle_partially_feasible(parsed_prompt)

        # Route to action handlers
        handlers = {
            "add_to_cart": lambda: self._handle_add_to_cart(parsed_prompt, customer_id, cart),
            "view_cart": lambda: self._handle_view_cart(cart),
            "view_inventory": lambda: self._handle_view_inventory(),
            "view_order_history": lambda: self._handle_view_order_history(customer_id),
            "view_profile": lambda: self._handle_view_profile(customer_id),
            "update_profile": lambda: self._handle_update_profile(parsed_prompt, customer_id),
            "clear_cart": lambda: self._handle_clear_cart(cart),
            "remove_from_cart": lambda: self._handle_remove_from_cart(parsed_prompt, cart),
            "checkout": lambda: self._handle_checkout(cart),
            "send_receipt": lambda: self._handle_send_receipt(customer_id),
            "out_of_scope": lambda: self._handle_out_of_scope(parsed_prompt),
        }

        handler = handlers.get(action_type, lambda: self._handle_out_of_scope(parsed_prompt))
        return handler()

    def _handle_add_to_cart(self, prompt: dict, customer_id: str, cart: dict) -> dict:
        """Add items to cart with validation"""
        items = prompt.get("extracted_items", [])
        if not items:
            return {
                "success": False,
                "message": "No items found to add",
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
                "message": f"⚠️ {', '.join(invalid_items)}",
                "action": None,
                "requires_confirmation": False,
                "alternatives": ["Try a different quantity or item"]
            }

        # Build preview message
        message = "Ready to add:\n\n"
        for item in preview_items:
            message += f"• {item['name']}: {item['quantity']}{item['unit']} = ₹{item['subtotal']:.2f}\n"
        message += f"\nTotal: ₹{total_price:.2f}"

        if invalid_items:
            message += f"\n\n⚠️ Note: {', '.join(invalid_items)}"

        return {
            "success": True,
            "message": message,
            "action": "add_to_cart",
            "requires_confirmation": True,
            "preview": {
                "items": preview_items,
                "total": total_price,
                "invalid_items": invalid_items
            },
            "redirect_to": "/customer/checkout"
        }

    def _handle_view_cart(self, cart: dict) -> dict:
        """Show current cart contents"""
        if not cart:
            return {
                "success": True,
                "message": "Your cart is empty. Start shopping? [View Items]",
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

        message = f"Your cart ({len(items)} items):\n\n"
        for item in items:
            message += f"• {item['name']}: {item['quantity']}{item['unit']} = ₹{item['subtotal']:.2f}\n"
        message += f"\nTotal: ₹{total:.2f}\n\n[Checkout] [Keep Shopping]"

        return {
            "success": True,
            "message": message,
            "action": "view_cart",
            "requires_confirmation": False,
            "preview": {"items": items, "total": total},
            "redirect_to": "/customer/cart"
        }

    def _handle_view_inventory(self) -> dict:
        """List all available items"""
        groceries = get_all_rows(GROCERIES_FILE)
        
        # Group by category
        by_category = {}
        for g in groceries:
            cat = g.get("Category", "Other")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(g)

        message = "Available items:\n\n"
        for category, items in by_category.items():
            message += f"📦 {category.upper()}\n"
            for item in items:
                stock = int(item["QuantityInStock"])
                status = "✅" if stock > 0 else "❌"
                message += f"  {status} {item['Name']}: ₹{item['PricePerUnit']}/{item.get('Unit', 'unit')} (Stock: {stock})\n"
            message += "\n"

        message += "[Add Items] [View Cart]"

        return {
            "success": True,
            "message": message,
            "action": "view_inventory",
            "requires_confirmation": False,
            "redirect_to": "/customer/dashboard"
        }

    def _handle_view_order_history(self, customer_id: str) -> dict:
        """Fetch and display order history"""
        from google_sheets_helpers import parse_transaction_history
        
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": "Could not find customer",
                "action": None
            }

        orders = parse_transaction_history(customer.get("TransactionHistory", "[]"))
        if not orders:
            return {
                "success": True,
                "message": "No orders yet. Start shopping! [Browse Items]",
                "action": "view_order_history",
                "requires_confirmation": False,
                "redirect_to": "/customer/dashboard"
            }

        message = f"Your orders ({len(orders)} total):\n\n"
        for order in reversed(orders[-5:]):  # Last 5 orders
            message += f"Order #{order.get('order_id', 'N/A')}: {order.get('timestamp', 'N/A')}\n"
            message += f"  Items: {len(order.get('line_items', []))}\n"
            message += f"  Total: ₹{order.get('total', 0):.2f}\n"
            message += f"  Payment: {order.get('payment_method', 'Unknown')}\n\n"

        message += "[View Full History] [Place New Order]"

        return {
            "success": True,
            "message": message,
            "action": "view_order_history",
            "requires_confirmation": False,
            "redirect_to": "/customer/history"
        }

    def _handle_view_profile(self, customer_id: str) -> dict:
        """Show user profile"""
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": "Could not find profile",
                "action": None
            }

        message = "Your profile:\n\n"
        message += f"Name: {customer.get('Name', 'N/A')}\n"
        message += f"Email: {customer.get('Email', 'N/A')}\n"
        message += f"Phone: {customer.get('Phone', 'N/A')}\n\n"
        message += "[Edit Profile] [Change Password]"

        return {
            "success": True,
            "message": message,
            "action": "view_profile",
            "requires_confirmation": False,
            "redirect_to": "/customer/profile"
        }

    def _handle_update_profile(self, prompt: dict, customer_id: str) -> dict:
        """Update profile (show preview, require confirmation)"""
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": "Could not find profile",
                "action": None
            }

        change = prompt.get("extracted_profile_change", {})
        field = change.get("field", "")
        new_value = change.get("value", "")

        if not field or not new_value:
            return {
                "success": False,
                "message": "Could not understand what to change. Try: 'Update my phone to 9876543210'",
                "action": None
            }

        current_value = customer.get(field.capitalize() if field == "phone" else field, "N/A")

        message = f"Update profile:\n\n"
        message += f"Field: {field}\n"
        message += f"Current: {current_value}\n"
        message += f"New: {new_value}\n\n"
        message += "⚠️ For security, confirm this change on the profile page."

        return {
            "success": True,
            "message": message,
            "action": "update_profile",
            "requires_confirmation": True,
            "preview": {
                "field": field,
                "current": current_value,
                "new": new_value
            },
            "redirect_to": "/customer/profile"
        }

    def _handle_clear_cart(self, cart: dict) -> dict:
        """Clear entire cart"""
        if not cart:
            return {
                "success": True,
                "message": "Cart is already empty",
                "action": None
            }

        return {
            "success": True,
            "message": f"Clear cart? This will remove {len(cart)} items.",
            "action": "clear_cart",
            "requires_confirmation": True,
            "preview": {"items_to_remove": len(cart)},
            "redirect_to": "/customer/dashboard"
        }

    def _handle_remove_from_cart(self, prompt: dict, cart: dict) -> dict:
        """Remove specific item from cart"""
        items = prompt.get("extracted_items", [])
        if not items:
            return {
                "success": False,
                "message": "Which item to remove?",
                "action": None
            }

        item_name = items[0]["name"]
        grocery = self._find_item(item_name)
        
        if not grocery:
            return {
                "success": False,
                "message": f"Item '{item_name}' not found",
                "action": None
            }

        item_id = str(grocery["ItemID"])
        if item_id not in cart:
            return {
                "success": False,
                "message": f"{item_name} is not in your cart",
                "action": None
            }

        return {
            "success": True,
            "message": f"Remove {item_name} from cart?",
            "action": "remove_from_cart",
            "requires_confirmation": True,
            "preview": {"item_id": item_id, "item_name": item_name},
            "redirect_to": "/customer/cart"
        }

    def _handle_checkout(self, cart: dict) -> dict:
        """Proceed to checkout"""
        if not cart:
            return {
                "success": False,
                "message": "Your cart is empty. Add items first!",
                "action": None
            }

        total = 0
        for item_id, qty in cart.items():
            grocery = get_row_by_id(GROCERIES_FILE, "ItemID", item_id)
            if grocery:
                total += float(grocery["PricePerUnit"]) * qty

        return {
            "success": True,
            "message": f"Proceed to checkout? Total: ₹{total:.2f}",
            "action": "checkout",
            "requires_confirmation": True,
            "preview": {"total": total, "items": len(cart)},
            "redirect_to": "/customer/checkout"
        }

    def _handle_send_receipt(self, customer_id: str) -> dict:
        """Auto-send receipt (no confirmation needed)"""
        from google_sheets_helpers import parse_transaction_history
        
        customer = get_row_by_id(CUSTOMERS_FILE, "CustomerID", customer_id)
        if not customer:
            return {
                "success": False,
                "message": "Could not find customer",
                "action": None
            }

        orders = parse_transaction_history(customer.get("TransactionHistory", "[]"))
        if not orders:
            return {
                "success": False,
                "message": "No orders to send receipt for",
                "action": None
            }

        # Get latest order
        latest = orders[-1]
        return {
            "success": True,
            "message": f"Sending receipt for Order #{latest.get('order_id')} to {customer.get('Email')}...\n\n✅ Receipt sent!",
            "action": "send_receipt",
            "requires_confirmation": False,
            "auto_execute": True,
            "preview": {"order_id": latest.get("order_id"), "total": latest.get("total")}
        }

    def _handle_out_of_scope(self, prompt: dict) -> dict:
        """Handle out of scope queries"""
        reason = prompt.get("reason_if_not_feasible", "unrelated query")
        
        if "unrelated" in reason.lower() or "weather" in reason.lower():
            message = "Sorry, I only help with FreshCart grocery orders!\n\nCan I help you:\n[Browse Items] [View Cart] [Order History]?"
        else:
            message = f"I can't help with that right now.\n\n{reason}\n\nTry something else?"

        return {
            "success": True,
            "message": message,
            "action": "out_of_scope",
            "requires_confirmation": False,
            "redirect_to": "/customer/dashboard"
        }

    def _handle_not_feasible(self, prompt: dict) -> dict:
        """Handle feasible but not possible requests"""
        reason = prompt.get("reason_if_not_feasible", "This is not possible right now")
        alternatives = prompt.get("alternatives", [])

        message = f"⚠️ {reason}\n\n"
        if alternatives:
            message += "Alternatives:\n"
            for alt in alternatives[:3]:
                message += f"• {alt}\n"

        return {
            "success": True,
            "message": message,
            "action": None,
            "requires_confirmation": False
        }

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
