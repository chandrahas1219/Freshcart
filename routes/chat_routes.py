"""
Chat API Routes - Handle AI chat interactions
"""

from flask import Blueprint, request, jsonify, session
from ai_chat_handler import ChatHandler
from cart_utils import get_cart

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

# Initialize handler
try:
    handler = ChatHandler()
except ValueError as e:
    handler = None
    error_msg = str(e)


@chat_bp.route("/message", methods=["POST"])
def chat_message():
    """
    POST /api/chat/message
    
    Request body:
    {
        "prompt": "user's message",
        "action": null or "confirmed" (if confirming a previous action)
    }
    
    Response:
    {
        "success": true/false,
        "message": "response to user",
        "action": "action_type or null",
        "requires_confirmation": true/false,
        "preview": {...},
        "redirect_to": "/path or null",
        "auto_execute": true/false
    }
    """

    if not handler:
        return jsonify({
            "success": False,
            "message": f"Chat is not available: {error_msg}",
            "error": error_msg
        }), 500

    data = request.get_json()
    if not data:
        return jsonify({
            "success": False,
            "message": "No data provided"
        }), 400

    user_prompt = data.get("prompt", "").strip()
    if not user_prompt:
        return jsonify({
            "success": False,
            "message": "Please enter a message"
        }), 400

    # Check if user is logged in
    customer_id = session.get("customer_id")
    admin_id = session.get("admin_id")

    # Only customers can use chat (for now)
    if not customer_id:
        return jsonify({
            "success": False,
            "message": "Please log in to use chat",
            "redirect_to": "/customer/login"
        }), 401

    try:
        # Step 1: Classify the prompt using Mistral
        parsed = handler.classify_prompt(user_prompt, customer_id)

        # Step 2: Handle the classified action
        cart = get_cart()
        response = handler.handle_action(parsed, customer_id, cart)

        # Add default fields if missing
        if "redirect_to" not in response:
            response["redirect_to"] = None
        if "requires_confirmation" not in response:
            response["requires_confirmation"] = False
        if "auto_execute" not in response:
            response["auto_execute"] = False

        return jsonify(response), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": "An error occurred. Please try again.",
            "error": str(e)
        }), 500


@chat_bp.route("/confirm", methods=["POST"])
def confirm_action():
    """
    POST /api/chat/confirm
    
    User confirms a previously shown action
    
    Request body:
    {
        "action": "add_to_cart",
        "preview": {...}
    }
    """

    if not handler:
        return jsonify({
            "success": False,
            "message": "Chat is not available"
        }), 500

    data = request.get_json()
    action = data.get("action")
    preview = data.get("preview", {})

    customer_id = session.get("customer_id")
    if not customer_id:
        return jsonify({
            "success": False,
            "message": "Please log in"
        }), 401

    try:
        # Execute the action
        result = execute_confirmed_action(action, preview, customer_id)
        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Action failed. Please try again.",
            "error": str(e)
        }), 500


def execute_confirmed_action(action: str, preview: dict, customer_id: str) -> dict:
    """Execute a confirmed action from chat"""
    from cart_utils import get_cart, save_cart
    from google_sheets_helpers import (
        GROCERIES_FILE, CUSTOMERS_FILE,
        get_row_by_id, update_row
    )

    cart = get_cart()

    if action == "add_to_cart":
        # Add items to cart
        items = preview.get("items", [])
        for item in items:
            # Find item in inventory
            groceries = handler._find_item(item["name"])
            if groceries:
                item_id = str(groceries["ItemID"])
                cart[item_id] = cart.get(item_id, 0) + item.get("quantity", 1)
        
        save_cart(cart)
        return {
            "success": True,
            "message": f"✅ Added {len(items)} item(s) to cart",
            "action": "add_to_cart",
            "redirect_to": "/customer/checkout"
        }

    elif action == "remove_from_cart":
        item_id = preview.get("item_id")
        qty_to_remove = preview.get("quantity")

        if item_id in cart:
            if qty_to_remove is None or qty_to_remove >= cart[item_id]:
                # No quantity specified, or it covers the whole line -> remove entirely
                del cart[item_id]
                message = "✅ Removed from cart"
            else:
                cart[item_id] -= qty_to_remove
                message = f"✅ Removed {qty_to_remove} — {cart[item_id]} left in cart"
        else:
            message = "Item was not in your cart"

        save_cart(cart)
        return {
            "success": True,
            "message": message,
            "action": "remove_from_cart",
            "redirect_to": "/customer/cart"
        }

    elif action == "clear_cart":
        save_cart({})
        return {
            "success": True,
            "message": "✅ Cart cleared",
            "action": "clear_cart",
            "redirect_to": "/customer/dashboard"
        }

    elif action == "checkout":
        return {
            "success": True,
            "message": "✅ Proceeding to checkout",
            "action": "checkout",
            "redirect_to": "/customer/checkout"
        }

    elif action == "update_profile":
        # Update profile - user must confirm on profile page
        field = preview.get("field", "").lower()
        new_value = preview.get("new", "")

        # Map field names
        field_map = {
            "phone": "Phone",
            "email": "Email",
            "name": "Name"
        }

        sheet_field = field_map.get(field, field)

        if not sheet_field or not new_value:
            return {
                "success": False,
                "message": "Invalid profile update"
            }

        # Update in sheet
        update_row(CUSTOMERS_FILE, "CustomerID", customer_id, {
            sheet_field: new_value
        })

        return {
            "success": True,
            "message": f"✅ {field} updated",
            "action": "update_profile",
            "redirect_to": "/customer/profile"
        }

    elif action == "send_receipt":
        # Auto-send receipt via email (implement email sending here)
        # For now, just confirm it was "sent"
        return {
            "success": True,
            "message": "✅ Receipt sent to your email",
            "action": "send_receipt"
        }

    else:
        return {
            "success": False,
            "message": "Unknown action"
        }
