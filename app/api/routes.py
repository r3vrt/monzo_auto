"""
API routes for Monzo OAuth integration. No HTML or business logic here.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_from_directory, session

from app.automation.integration import AutomationIntegration
from app.automation.pot_manager import PotManager
from app.db import get_db_session
from app.models import Account, Pot, Transaction, User, UserPotCategory
from app.monzo.sync import sync_account_data, sync_bills_pot_transactions
from app.services.auth_service import get_authenticated_monzo_client


def get_user_id_from_auth():
    """
    Get user_id from session or fall back to the most recent user in database.
    Returns user_id string or None if no user found.
    """
    user_id = session.get("user_id")
    if user_id:
        return user_id

    # Fall back to most recent user in database
    with next(get_db_session()) as db:
        user = db.query(User).order_by(User.id.desc()).first()
        if user:
            return str(user.monzo_user_id)

    return None


api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)


@api_bp.route("/accounts", methods=["GET"])
def get_accounts():
    """
    Get all active accounts for the current user.
    Returns list of accounts that have been imported.
    """
    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")
        accounts = db.query(Account).filter_by(user_id=user_id, is_active=True).all()
        return jsonify(
            {
                "accounts": [
                    {
                        "id": acc.id,
                        "name": acc.description or acc.id,
                        "type": acc.type,
                        "is_active": acc.is_active,
                    }
                    for acc in accounts
                ]
            }
        )


@api_bp.route("/accounts/select", methods=["GET"])
def accounts_select():
    """
    Fetch Monzo accounts for the authenticated user using tokens from database.
    Returns a list of accounts for user selection (to be rendered by frontend).
    """
    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        try:
            accounts = monzo.get_accounts()  # Returns list of Account objects
            accounts_list = [
                {
                    "id": acc.id,
                    "name": acc.description,
                    "type": acc.type,
                    "closed": acc.closed,
                }
                for acc in accounts
            ]
            return jsonify({"accounts": accounts_list})
        except Exception as e:
            return jsonify({"error": f"Failed to fetch accounts: {str(e)}"}), 500


@api_bp.route("/accounts/available", methods=["GET"])
def accounts_available():
    """
    Fetch all Monzo accounts for the authenticated user, with is_active status from DB.
    """
    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        try:
            accounts = monzo.get_accounts()
            user_id = monzo.tokens.get("user_id")
            db_accounts = {
                a.id: a for a in db.query(Account).filter_by(user_id=user_id).all()
            }
            accounts_list = []
            for acc in accounts:
                db_acc = db_accounts.get(acc.id)
                accounts_list.append(
                    {
                        "id": acc.id,
                        "name": acc.description,
                        "type": acc.type,
                        "closed": acc.closed,
                        "is_active": bool(db_acc.is_active) if db_acc else False,
                    }
                )
            return jsonify({"accounts": accounts_list})
        except Exception as e:
            return jsonify({"error": f"Failed to fetch accounts: {str(e)}"}), 500


@api_bp.route("/accounts/select", methods=["POST"])
def accounts_select_post():
    """
    Accept selected account IDs from the user and trigger data import.
    Expects JSON: {"account_ids": [ ... ], "account_names": { ... }}
    """
    data = request.get_json()
    selected_account_ids = data.get("account_ids", [])
    account_names = data.get("account_names", {})

    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")

        for acc_id in selected_account_ids:
            acc = db.query(Account).filter_by(id=acc_id, user_id=user_id).first()
            custom_name = account_names.get(acc_id)
            if acc is not None:
                if acc.is_active is not True:
                    acc.is_active = True
                if custom_name is not None and custom_name != "":
                    acc.description = custom_name
            else:
                acc = Account(
                    id=acc_id,
                    user_id=user_id,
                    description=custom_name or "",
                    type="",
                    created=datetime.now(timezone.utc),
                    closed=0,
                    is_active=True,
                )
                db.add(acc)
        db.commit()
        # Trigger sync for these accounts
        accounts_api = {a.id: a for a in monzo.get_accounts()}
        logger.info(f"[DEBUG] Monzo API returned accounts: {list(accounts_api.keys())}")
        errors = []
        for acc_id in selected_account_ids:
            try:
                # Update account details if available
                acc = db.query(Account).filter_by(id=acc_id, user_id=user_id).first()
                api_acc = accounts_api.get(acc_id)
                if acc is not None and api_acc is not None:
                    logger.info(
                        f"[DEBUG] Updating account {acc_id} with Monzo API data: {api_acc.description}, {api_acc.type}"
                    )
                    if acc.description is None or acc.description == "":
                        acc.description = api_acc.description
                    acc.type = api_acc.type
                    acc.closed = int(api_acc.closed)
                    acc.updated_at = getattr(
                        api_acc, "updated_at", datetime.now(timezone.utc)
                    )
                logger.info(f"[DEBUG] Syncing account {acc_id}")
                sync_account_data(db, str(acc.user_id), str(acc.id), monzo)
            except Exception as e:
                logger.error(f"[ERROR] Failed to sync account {acc_id}: {e}")
                errors.append(f"Account {acc_id}: {e}")
        db.commit()
    if errors:
        return jsonify({"success": False, "errors": errors}), 500
    return jsonify(
        {"success": True, "import_started": True, "accounts": selected_account_ids}
    )


@api_bp.route("/accounts/add", methods=["POST"])
def accounts_add():
    """
    Add more accounts for syncing. Expects {"account_ids": [...]}. Only activates new accounts.
    """
    data = request.get_json()
    add_account_ids = data.get("account_ids", [])

    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")
        for acc_id in add_account_ids:
            acc = db.query(Account).filter_by(id=acc_id, user_id=user_id).first()
            if acc is not None and acc.is_active is True:
                continue  # Already active
            elif acc is not None:
                acc.is_active = True
            else:
                acc = Account(
                    id=acc_id,
                    user_id=user_id,
                    description="",
                    type="",
                    created=datetime.now(timezone.utc),
                    closed=0,
                    is_active=True,
                )
                db.add(acc)
        db.commit()
        # Trigger sync for these new accounts
        accounts_api = {a.id: a for a in monzo.get_accounts()}
        logger.info(f"[DEBUG] Monzo API returned accounts: {list(accounts_api.keys())}")
        errors = []
        for acc_id in add_account_ids:
            try:
                acc = db.query(Account).filter_by(id=acc_id, user_id=user_id).first()
                api_acc = accounts_api.get(acc_id)
                if acc is not None and api_acc is not None:
                    logger.info(
                        f"[DEBUG] Updating account {acc_id} with Monzo API data: {api_acc.description}, {api_acc.type}"
                    )
                    if acc.description is None or acc.description == "":
                        acc.description = api_acc.description
                    acc.type = api_acc.type
                    acc.closed = int(api_acc.closed)
                    acc.updated_at = getattr(
                        api_acc, "updated_at", datetime.now(timezone.utc)
                    )
                logger.info(f"[DEBUG] Syncing account {acc_id}")
                sync_account_data(db, str(acc.user_id), str(acc.id), monzo)
            except Exception as e:
                logger.error(f"[ERROR] Failed to sync account {acc_id}: {e}")
                errors.append(f"Account {acc_id}: {e}")
        db.commit()
    if errors:
        return jsonify({"success": False, "errors": errors}), 500
    return jsonify({"success": True, "accounts_added": add_account_ids})


@api_bp.route("/sync_all", methods=["POST"])
def sync_all_accounts():
    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"success": False, "error": "No authenticated user found."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")
        accounts = db.query(Account).filter_by(user_id=user_id, is_active=True).all()
        results = []
        for acc in accounts:
            try:
                sync_account_data(db, str(acc.user_id), str(acc.id), monzo)
                results.append({"account_id": acc.id, "status": "success"})
            except Exception as e:
                results.append({"account_id": acc.id, "status": f"error: {e}"})
        
        # After normal sync, also sync bills pot if it exists
        bills_pot = db.query(Pot).filter_by(name="Bills", user_id=user_id, deleted=0).first()
        bills_sync_result = {"bills_pot": "not_found"}
        
        if bills_pot:
            try:
                success = sync_bills_pot_transactions(db, user_id, bills_pot.id, monzo)
                bills_sync_result = {"bills_pot": "success" if success else "error"}
            except Exception as e:
                bills_sync_result = {"bills_pot": f"error: {e}"}
        
        return jsonify({"success": True, "results": results, "bills_sync": bills_sync_result})


# ============================================================================
# Pot Category Management API Endpoints
# ============================================================================


@api_bp.route("/pots/categories", methods=["GET"])
def get_pot_categories():
    """
    Get all pot categories and their associated pots for the authenticated user.
    Returns a structured view of pots organized by category.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        # Get all pots for the user
        pots = db.query(Pot).filter_by(user_id=user_id, deleted=0).all()

        # Get all category assignments
        category_assignments = (
            db.query(UserPotCategory).filter_by(user_id=user_id).all()
        )
        category_map = {}
        for assignment in category_assignments:
            if assignment.category not in category_map:
                category_map[assignment.category] = []
            category_map[assignment.category].append(assignment.pot_id)

        # Build response with pot details
        categories = {}
        for category, pot_ids in category_map.items():
            categories[category] = []
            for pot_id in pot_ids:
                pot = next((p for p in pots if p.id == pot_id), None)
                if pot:
                    categories[category].append(
                        {
                            "id": pot.id,
                            "name": pot.name,
                            "balance": pot.balance,
                            "currency": pot.currency,
                            "style": pot.style,
                        }
                    )

        # Add uncategorized pots
        categorized_pot_ids = set()
        for pot_ids in category_map.values():
            categorized_pot_ids.update(pot_ids)

        uncategorized = []
        for pot in pots:
            if pot.id not in categorized_pot_ids:
                uncategorized.append(
                    {
                        "id": pot.id,
                        "name": pot.name,
                        "balance": pot.balance,
                        "currency": pot.currency,
                        "style": pot.style,
                    }
                )

        # Get available categories from PotManager
        pot_manager = PotManager(db, None)  # We don't need monzo_client for this
        available_categories = pot_manager.get_available_categories()

        return jsonify(
            {
                "categories": categories,
                "uncategorized": uncategorized,
                "available_categories": available_categories,
            }
        )


@api_bp.route("/pots/categories", methods=["POST"])
def assign_pot_category():
    """
    Assign a pot to a specific category.
    Expects JSON: {"pot_id": "...", "category": "..."}
    """
    data = request.get_json()
    pot_id = data.get("pot_id")
    category = data.get("category")

    if not pot_id or not category:
        return jsonify({"error": "Missing pot_id or category"}), 400

    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        # Validate category using PotManager
        pot_manager = PotManager(db, None)
        valid_categories = pot_manager.get_available_categories()
        if category not in valid_categories:
            return (
                jsonify(
                    {"error": f"Invalid category. Must be one of: {valid_categories}"}
                ),
                400,
            )

        # Verify pot exists and belongs to user
        pot = db.query(Pot).filter_by(id=pot_id, user_id=user_id, deleted=0).first()
        if not pot:
            return jsonify({"error": "Pot not found or doesn't belong to user"}), 404

        # Check if assignment already exists
        existing = (
            db.query(UserPotCategory)
            .filter_by(user_id=user_id, pot_id=pot_id, category=category)
            .first()
        )

        if existing:
            return jsonify({"message": "Pot already assigned to this category"}), 200

        # Create new assignment
        assignment = UserPotCategory(user_id=user_id, pot_id=pot_id, category=category)

        db.add(assignment)
        db.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Pot '{pot.name}' assigned to category '{category}'",
            }
        )


@api_bp.route("/pots/categories", methods=["DELETE"])
def remove_pot_category():
    """
    Remove a pot from a specific category.
    Expects JSON: {"pot_id": "...", "category": "..."}
    """
    data = request.get_json()
    pot_id = data.get("pot_id")
    category = data.get("category")

    if not pot_id or not category:
        return jsonify({"error": "Missing pot_id or category"}), 400

    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        # Find the assignment
        assignment = (
            db.query(UserPotCategory)
            .filter_by(user_id=user_id, pot_id=pot_id, category=category)
            .first()
        )

        if not assignment:
            return jsonify({"error": "Pot not found in this category"}), 404

        # Get pot name for response
        pot = db.query(Pot).filter_by(id=pot_id).first()
        pot_name = pot.name if pot else pot_id

        # Remove the assignment
        db.delete(assignment)
        db.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Pot '{pot_name}' removed from category '{category}'",
            }
        )


@api_bp.route("/pots/categories/<category>", methods=["GET"])
def get_pots_by_category(category):
    """
    Get all pots in a specific category for the authenticated user.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        # Validate category using PotManager
        pot_manager = PotManager(db, None)
        valid_categories = pot_manager.get_available_categories()
        if category not in valid_categories:
            return (
                jsonify(
                    {"error": f"Invalid category. Must be one of: {valid_categories}"}
                ),
                400,
            )

        # Get pot IDs for this category
        assignments = (
            db.query(UserPotCategory)
            .filter_by(user_id=user_id, category=category)
            .all()
        )

        pot_ids = [assignment.pot_id for assignment in assignments]

        # Get pot details
        pots = (
            db.query(Pot)
            .filter(Pot.id.in_(pot_ids), Pot.user_id == user_id, Pot.deleted == 0)
            .all()
        )

        pots_data = []
        for pot in pots:
            pots_data.append(
                {
                    "id": pot.id,
                    "name": pot.name,
                    "balance": pot.balance,
                    "currency": pot.currency,
                    "style": pot.style,
                    "created": pot.created.isoformat() if pot.created else None,
                    "updated": pot.updated.isoformat() if pot.updated else None,
                }
            )

        return jsonify(
            {
                "category": category,
                "pots": pots_data,
                "total_balance": sum(pot.balance for pot in pots),
            }
        )


@api_bp.route("/test/create-rule")
def test_create_rule():
    """Test page for create rule functionality."""
    return send_from_directory('.', 'test_create_rule.html')

@api_bp.route("/pots", methods=["GET"])
def get_all_pots():
    """
    Get all pots for the authenticated user in a simple format for automation forms.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        pots = (
            db.query(Pot)
            .filter_by(user_id=user_id, deleted=0)
            .order_by(Pot.name)
            .all()
        )

        pots_data = [
            {
                "id": pot.id,
                "name": pot.name,
                "balance": pot.balance,
                "currency": pot.currency,
                "style": pot.style,
                # Check if pot has goal information
                "has_goal": hasattr(pot, 'goal') and pot.goal and pot.goal > 0,
                "goal_amount": getattr(pot, 'goal', None),
            }
            for pot in pots
        ]

        return jsonify({"pots": pots_data})


@api_bp.route("/pots/balances", methods=["GET"])
def get_pot_balances():
    """
    Get pot balances aggregated by category for the authenticated user.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        # Get all category assignments
        assignments = db.query(UserPotCategory).filter_by(user_id=user_id).all()

        # Group by category
        category_balances = {}
        for assignment in assignments:
            if assignment.category not in category_balances:
                category_balances[assignment.category] = {
                    "pots": [],
                    "total_balance": 0,
                }

            # Get pot details
            pot = (
                db.query(Pot)
                .filter_by(id=assignment.pot_id, user_id=user_id, deleted=0)
                .first()
            )

            if pot:
                category_balances[assignment.category]["pots"].append(
                    {
                        "id": pot.id,
                        "name": pot.name,
                        "balance": pot.balance,
                        "currency": pot.currency,
                    }
                )
                category_balances[assignment.category]["total_balance"] += pot.balance

        # Add uncategorized pots
        categorized_pot_ids = set()
        for assignment in assignments:
            categorized_pot_ids.add(assignment.pot_id)

        uncategorized_pots = (
            db.query(Pot)
            .filter(
                Pot.user_id == user_id,
                Pot.deleted == 0,
                ~Pot.id.in_(categorized_pot_ids),
            )
            .all()
        )

        uncategorized_total = sum(pot.balance for pot in uncategorized_pots)

        return jsonify(
            {
                "category_balances": category_balances,
                "uncategorized": {
                    "pots": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "balance": p.balance,
                            "currency": p.currency,
                        }
                        for p in uncategorized_pots
                    ],
                    "total_balance": uncategorized_total,
                },
                "summary": {
                    "total_categorized": sum(
                        cat["total_balance"] for cat in category_balances.values()
                    ),
                    "total_uncategorized": uncategorized_total,
                    "total_all": sum(
                        cat["total_balance"] for cat in category_balances.values()
                    )
                    + uncategorized_total,
                },
            }
        )


# ============================================================================
# Automation Management API Endpoints
# ============================================================================


@api_bp.route("/automation/status", methods=["GET"])
def get_automation_status():
    """
    Get automation status for the authenticated user.
    """
    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")
        automation = AutomationIntegration(db, monzo)
        status = automation.get_automation_status(user_id)

        return jsonify(status)


@api_bp.route("/automation/execute", methods=["POST"])
def execute_automation():
    """
    Manually trigger automation execution for the authenticated user.
    """
    data = request.get_json() or {}
    account_id = data.get("account_id")

    if not account_id:
        return jsonify({"error": "Missing account_id"}), 400

    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")

        # Verify account belongs to user
        account = (
            db.query(Account)
            .filter_by(id=account_id, user_id=user_id, is_active=True)
            .first()
        )
        if not account:
            return jsonify({"error": "Account not found or not active"}), 404

        automation = AutomationIntegration(db, monzo)
        results = automation.execute_post_sync_automation(user_id, account_id)

        return jsonify(
            {
                "success": True,
                "message": "Automation executed successfully",
                "results": results,
            }
        )


@api_bp.route("/automation/rules", methods=["GET"])
def get_automation_rules():
    """
    Get all automation rules for the authenticated user.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager

        rules_manager = RulesManager(db)
        rules = rules_manager.get_rules_by_user(user_id)

        rules_data = []
        for rule in rules:
            # Get execution metadata from database
            execution_metadata = rule.execution_metadata or {}
            last_result = execution_metadata.get("last_result", {})
            last_trigger_reason = execution_metadata.get("last_trigger_reason", "Unknown")
            execution_count = execution_metadata.get("execution_count", 0)
            

            
            rules_data.append(
                {
                    "id": rule.rule_id,  # Use rule_id instead of database id
                    "name": rule.name,
                    "rule_type": rule.rule_type,
                    "enabled": rule.enabled,
                    "config": rule.config,
                    "last_executed": (
                        rule.last_executed.isoformat() if rule.last_executed else None
                    ),
                    "created_at": (
                        rule.created_at.isoformat() if rule.created_at else None
                    ),
                    "execution_metadata": {
                        "last_result": last_result,
                        "last_trigger_reason": last_trigger_reason,
                        "execution_count": execution_count
                    }
                }
            )

        return jsonify({"rules": rules_data, "total": len(rules_data)})


@api_bp.route("/automation/rules", methods=["POST"])
def create_automation_rule():
    """
    Create a new automation rule for the authenticated user.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing rule data"}), 400

    required_fields = ["name", "rule_type", "config"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager

        rules_manager = RulesManager(db)

        import uuid

        rule_data = {
            "rule_id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": data["name"],
            "rule_type": data["rule_type"],
            "config": data["config"],
            "enabled": data.get("enabled", True),
        }

        rule = rules_manager.create_rule(rule_data)

        if rule:
            # Add scheduler for this rule if it has specific timing requirements
            try:
                from run import add_rule_scheduler
                # Get user's account
                accounts = db.query(Account).filter_by(user_id=user_id, is_active=True).all()
                if accounts:
                    add_rule_scheduler(rule.rule_id, user_id, str(accounts[0].id), data["config"])
            except Exception as e:
                logging.error(f"Error adding scheduler for new rule {rule.rule_id}: {e}")
            
            return jsonify(
                {
                    "success": True,
                    "message": "Automation rule created successfully",
                    "rule_id": rule.rule_id,
                }
            )
        else:
            return jsonify({"error": "Failed to create automation rule"}), 500


@api_bp.route("/automation/rules/<rule_id>", methods=["GET"])
def get_automation_rule(rule_id):
    """
    Get a specific automation rule by ID.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager

        rules_manager = RulesManager(db)
        rule = rules_manager.get_rule_by_id(rule_id)

        if not rule or rule.user_id != user_id:
            return jsonify({"error": "Rule not found"}), 404

        return jsonify(
            {
                "id": rule.rule_id,
                "name": rule.name,
                "rule_type": rule.rule_type,
                "enabled": rule.enabled,
                "config": rule.config,
                "last_executed": (
                    rule.last_executed.isoformat() if rule.last_executed else None
                ),
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
            }
        )


@api_bp.route("/automation/rules/<rule_id>", methods=["PUT"])
def update_automation_rule(rule_id):
    """
    Update an existing automation rule.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing update data"}), 400

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager

        rules_manager = RulesManager(db)

        # Verify rule belongs to user
        rule = rules_manager.get_rule_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return jsonify({"error": "Rule not found"}), 404

        success = rules_manager.update_rule(rule_id, data)

        if success:
            return jsonify(
                {"success": True, "message": "Automation rule updated successfully"}
            )
        else:
            return jsonify({"error": "Failed to update automation rule"}), 500


@api_bp.route("/automation/rules/<rule_id>", methods=["DELETE"])
def delete_automation_rule(rule_id):
    """
    Delete an automation rule.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager

        rules_manager = RulesManager(db)

        # Verify rule belongs to user
        rule = rules_manager.get_rule_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return jsonify({"error": "Rule not found"}), 404

        success = rules_manager.delete_rule(rule_id)

        if success:
            # Remove scheduler for this rule
            try:
                from run import remove_rule_scheduler
                remove_rule_scheduler(rule_id)
            except Exception as e:
                logging.error(f"Error removing scheduler for deleted rule {rule_id}: {e}")
            
            return jsonify(
                {"success": True, "message": "Automation rule deleted successfully"}
            )
        else:
            return jsonify({"error": "Failed to delete automation rule"}), 500


@api_bp.route("/automation/rules/<rule_id>/toggle", methods=["POST"])
def toggle_automation_rule(rule_id):
    """
    Toggle the enabled state of an automation rule.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager

        rules_manager = RulesManager(db)

        # Verify rule belongs to user
        rule = rules_manager.get_rule_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return jsonify({"error": "Rule not found"}), 404

        success = rules_manager.toggle_rule(rule_id)

        if success:
            # Get the updated rule to get the new state
            updated_rule = rules_manager.get_rule_by_id(rule_id)
            
            # Update scheduler for this rule
            try:
                from run import update_rule_scheduler
                # Get user's account
                accounts = db.query(Account).filter_by(user_id=user_id, is_active=True).all()
                if accounts:
                    update_rule_scheduler(rule_id, user_id, str(accounts[0].id), updated_rule.config, updated_rule.enabled)
            except Exception as e:
                logging.error(f"Error updating scheduler for toggled rule {rule_id}: {e}")
            
            return jsonify(
                {
                    "success": True,
                    "message": "Automation rule toggled successfully",
                    "enabled": updated_rule.enabled,  # Return the actual new state
                }
            )
        else:
            return jsonify({"error": "Failed to toggle automation rule"}), 500


@api_bp.route("/automation/rules/<rule_id>/trigger", methods=["POST"])
def trigger_single_rule(rule_id):
    """
    Manually trigger a single automation rule.
    """
    user_id = get_user_id_from_auth()
    if not user_id:
        return jsonify({"error": "No user found. Please authenticate."}), 401

    with next(get_db_session()) as db:
        from app.automation.rules import RulesManager
        from app.automation.integration import AutomationIntegration

        rules_manager = RulesManager(db)
        rule = rules_manager.get_rule_by_id(rule_id)

        if not rule:
            return jsonify({"error": "Rule not found"}), 404

        if rule.user_id != user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if not rule.enabled:
            return jsonify({"error": "Cannot trigger disabled rule"}), 400

        try:
            # Get authenticated Monzo client
            monzo = get_authenticated_monzo_client(db)
            if not monzo:
                return jsonify({"error": "No authenticated Monzo client found"}), 401

            # Create automation integration instance
            automation = AutomationIntegration(db, monzo)
            
            # Get a default account for this user
            accounts = db.query(Account).filter_by(user_id=user_id, is_active=True).all()
            if not accounts:
                return jsonify({"error": "No active accounts found for user"}), 400
            
            account_id = str(accounts[0].id)
            
            # Execute the single rule
            result = automation.execute_single_rule(rule, user_id, account_id)
            
            if result.get("success"):
                return jsonify({
                    "success": True,
                    "message": f"Rule '{rule.name}' executed successfully",
                    "result": result
                })
            else:
                return jsonify({
                    "success": False,
                    "error": result.get("error", "Rule execution failed"),
                    "result": result
                })
                
        except Exception as e:
            logger.error(f"Error triggering rule {rule_id}: {e}")
            return jsonify({
                "success": False,
                "error": f"Error executing rule: {str(e)}"
            }), 500


@api_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """
    Get sync status for all accounts.
    Returns last sync time and basic sync information.
    """
    with next(get_db_session()) as db:
        monzo = get_authenticated_monzo_client(db)
        if not monzo:
            return (
                jsonify({"error": "No authenticated user found. Please authenticate."}),
                401,
            )

        user_id = monzo.tokens.get("user_id")
        # Get the latest transaction timestamp as last sync time
        latest_txn = (
            db.query(Transaction)
            .filter_by(user_id=user_id)
            .order_by(Transaction.id.desc())
            .first()
        )
        last_sync = latest_txn.created.isoformat() if latest_txn else None

        return jsonify({"last_sync": last_sync, "status": "ok"})


@api_bp.route("/sync_bills_pot", methods=["POST"])
def sync_bills_pot():
    """Sync transactions specifically for the bills pot."""
    try:
        # Get bills pot ID from request
        data = request.get_json()
        bills_pot_id = data.get("bills_pot_id")

        if not bills_pot_id:
            return jsonify({"success": False, "error": "bills_pot_id is required"}), 400

        # Initialize sync service
        with next(get_db_session()) as db:
            monzo = get_authenticated_monzo_client(db)
            if not monzo:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "No authenticated user found. Please authenticate.",
                        }
                    ),
                    401,
                )

            user_id = monzo.tokens.get("user_id")

            # Sync bills pot transactions
            success = sync_bills_pot_transactions(db, user_id, bills_pot_id, monzo)

            if success:
                return jsonify(
                    {
                        "success": True,
                        "message": "Bills pot transactions synced successfully",
                    }
                )
            else:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Failed to sync bills pot transactions",
                        }
                    ),
                    500,
                )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route('/automation/trigger', methods=['POST'])
def trigger_automation():
    """Manually trigger automation for testing purposes."""
    try:
        # Get current user using the same pattern as other automation endpoints
        user_id = get_user_id_from_auth()
        if not user_id:
            return jsonify({'error': 'No user found. Please authenticate.'}), 401
        
        # Get user's accounts
        with next(get_db_session()) as db:
            accounts = db.query(Account).filter_by(user_id=user_id, is_active=True).all()
            if not accounts:
                return jsonify({'error': 'No active accounts found'}), 404
            
            # Create Monzo client
            monzo = get_authenticated_monzo_client(db)
            if not monzo:
                return jsonify({'error': 'No valid Monzo credentials'}), 401
            
            # Create automation integration
            automation = AutomationIntegration(db, monzo)
            
            # Execute automation once per user - the system will determine appropriate accounts for each rule
            logging.info(f"[MANUAL] Manually triggering automation for user {user_id} (account-aware execution)")
            results = automation.execute_post_sync_automation(user_id, force_manual=True)
            all_results = {"user_automation": results}
            
            return jsonify({
                'message': 'Automation triggered manually',
                'results': all_results
            })
            
    except Exception as e:
        logging.error(f"[MANUAL] Error triggering automation: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/automation/queue/status', methods=['GET'])
def get_queue_status():
    """Get the current status of the automation queue."""
    try:
        from app.automation.queue_manager import get_queue_manager
        
        queue_manager = get_queue_manager()
        status = queue_manager.get_queue_status()
        
        return jsonify({
            'success': True,
            'queue_status': status
        })
        
    except Exception as e:
        logging.error(f"[QUEUE] Error getting queue status: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/automation/queue/clear', methods=['POST'])
def clear_queue():
    """Clear all items from the automation queue."""
    try:
        from app.automation.queue_manager import get_queue_manager
        
        queue_manager = get_queue_manager()
        queue_manager.clear_queue()
        
        return jsonify({
            'success': True,
            'message': 'Queue cleared successfully'
        })
        
    except Exception as e:
        logging.error(f"[QUEUE] Error clearing queue: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/automation/sweep/executions', methods=['GET'])
def get_sweep_executions():
    """Get execution count and history for sweep rules."""
    try:
        from app.automation.queue_manager import get_queue_manager
        
        queue_manager = get_queue_manager()
        status = queue_manager.get_queue_status()
        
        # Filter for sweep rules only
        sweep_executions = {}
        for rule_id, count in status.get("rule_execution_counts", {}).items():
            history = status.get("execution_history", {}).get(rule_id, {})
            if history.get("rule_type") == "pot_sweep":
                sweep_executions[rule_id] = {
                    "execution_count": count,
                    "last_execution": history.get("timestamp"),
                    "last_result": history.get("result", {})
                }
        
        return jsonify({
            'success': True,
            'sweep_executions': sweep_executions,
            'total_sweep_executions': sum(info["execution_count"] for info in sweep_executions.values())
        })
        
    except Exception as e:
        logging.error(f"[SWEEP] Error getting sweep executions: {e}")
        return jsonify({'error': str(e)}), 500
