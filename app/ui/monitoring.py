"""
Monitoring UI routes for automation health and system status.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any

from flask import render_template, request, jsonify, session
from sqlalchemy import func, desc

from app.db import get_db_session
from app.models import User
from app.automation.rules import AutomationRule
from app.services.auth_service import get_authenticated_monzo_client

logger = logging.getLogger(__name__)


def register_monitoring_routes(ui_bp):
    """Register monitoring routes with the UI blueprint."""
    
    @ui_bp.route("/monitoring/dashboard")
    def monitoring_dashboard():
        """
        Display automation monitoring dashboard.
        Shows system health, rule status, and execution history.
        """
        return render_template("monitoring/dashboard.html")

    @ui_bp.route("/monitoring/api/health")
    def monitoring_api_health():
        """
        Get automation system health metrics.
        Returns JSON with system status, rule counts, and recent execution data.
        """
        try:
            with next(get_db_session()) as db:
                # Get authenticated user
                monzo = get_authenticated_monzo_client(db)
                if not monzo:
                    return jsonify({"error": "No authenticated user found"}), 401
                
                user_id = monzo.tokens.get("user_id")
                
                # Get automation rules statistics
                total_rules = db.query(AutomationRule).filter_by(user_id=user_id).count()
                enabled_rules = db.query(AutomationRule).filter_by(user_id=user_id, enabled=True).count()
                disabled_rules = total_rules - enabled_rules
                
                # Get recent execution data (last 24 hours)
                since = datetime.now(timezone.utc) - timedelta(hours=24)
                recent_executions = db.query(AutomationRule).filter(
                    AutomationRule.user_id == user_id,
                    AutomationRule.last_executed >= since
                ).count()
                
                # Count failed executions by checking execution metadata in Python
                # (avoiding SQL LIKE on JSON column which can cause errors)
                recent_rules = db.query(AutomationRule).filter(
                    AutomationRule.user_id == user_id,
                    AutomationRule.last_executed >= since,
                    AutomationRule.execution_metadata.isnot(None)
                ).all()
                
                failed_executions = 0
                for rule in recent_rules:
                    try:
                        import json
                        if rule.execution_metadata:
                            if isinstance(rule.execution_metadata, str):
                                metadata = json.loads(rule.execution_metadata)
                            else:
                                metadata = rule.execution_metadata
                            if metadata.get("status") == "failed":
                                failed_executions += 1
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        # Skip rules with invalid metadata
                        continue
                
                # Calculate success rate
                success_rate = 100.0
                if recent_executions > 0:
                    successful_executions = recent_executions - failed_executions
                    success_rate = (successful_executions / recent_executions) * 100
                
                # Generate health status
                status = "healthy"
                if failed_executions > 0:
                    status = "warning" if failed_executions < 3 else "critical"
                elif disabled_rules > enabled_rules:
                    status = "warning"
                
                # Generate alerts
                alerts = _generate_health_alerts({
                    "status": status,
                    "total_rules": total_rules,
                    "enabled_rules": enabled_rules,
                    "disabled_rules": disabled_rules,
                    "recent_executions": recent_executions,
                    "failed_executions": failed_executions,
                    "success_rate": success_rate
                })
                
                return jsonify({
                    "status": status,
                    "metrics": {
                        "total_rules": total_rules,
                        "enabled_rules": enabled_rules,
                        "disabled_rules": disabled_rules,
                        "recent_executions": recent_executions,
                        "failed_executions": failed_executions,
                        "success_rate": round(success_rate, 1)
                    },
                    "alerts": alerts,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error getting health metrics: {e}")
            return jsonify({
                "status": "error",
                "error": "Failed to retrieve health metrics",
                "metrics": {
                    "total_rules": 0,
                    "enabled_rules": 0,
                    "disabled_rules": 0,
                    "recent_executions": 0,
                    "failed_executions": 0,
                    "success_rate": 0
                },
                "alerts": [{"type": "critical", "message": "Health monitoring unavailable"}]
            }), 500

    @ui_bp.route("/monitoring/api/execution-history")
    def monitoring_api_execution_history():
        """
        Get recent automation execution history.
        Returns detailed execution history for monitoring dashboard.
        """
        try:
            limit = request.args.get('limit', 50, type=int)
            limit = min(limit, 100)  # Cap at 100 for performance
            
            with next(get_db_session()) as db:
                # Get authenticated user
                monzo = get_authenticated_monzo_client(db)
                if not monzo:
                    return jsonify({"error": "No authenticated user found"}), 401
                
                user_id = monzo.tokens.get("user_id")
                
                # Get recent executions, ordered by most recent
                rules = db.query(AutomationRule).filter_by(
                    user_id=user_id
                ).filter(
                    AutomationRule.last_executed.isnot(None)
                ).order_by(
                    desc(AutomationRule.last_executed)
                ).limit(limit).all()
                
                executions = []
                for rule in rules:
                    # Parse execution metadata if available
                    metadata = {}
                    if rule.execution_metadata:
                        try:
                            import json
                            metadata = json.loads(rule.execution_metadata)
                        except (json.JSONDecodeError, TypeError):
                            metadata = {"raw": rule.execution_metadata}
                    
                    executions.append({
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "rule_type": rule.rule_type,
                        "executed_at": rule.last_executed.isoformat() if rule.last_executed else None,
                        "status": metadata.get("status", "unknown"),
                        "result": metadata.get("result", "No details available"),
                        "duration_ms": metadata.get("duration_ms"),
                        "error": metadata.get("error"),
                        "enabled": rule.enabled
                    })
                
                return jsonify({
                    "executions": executions,
                    "total_count": len(executions),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error getting execution history: {e}")
            return jsonify({
                "error": "Failed to retrieve execution history",
                "executions": []
            }), 500


def _generate_health_alerts(metrics: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Generate health alerts based on system metrics.
    
    Args:
        metrics: Dictionary containing health metrics
        
    Returns:
        List of alert dictionaries with type and message
    """
    alerts = []
    
    # Critical alerts
    if metrics["failed_executions"] >= 5:
        alerts.append({
            "type": "critical",
            "title": "High Failure Rate",
            "message": f"{metrics['failed_executions']} automation rules failed in the last 24 hours",
            "action": "Check logs and review rule configuration"
        })
    
    if metrics["success_rate"] < 50 and metrics["recent_executions"] > 0:
        alerts.append({
            "type": "critical", 
            "title": "Low Success Rate",
            "message": f"Only {metrics['success_rate']}% of automation executions succeeded",
            "action": "Review failed rules and fix configuration issues"
        })
    
    # Warning alerts
    if metrics["disabled_rules"] > metrics["enabled_rules"] and metrics["total_rules"] > 0:
        alerts.append({
            "type": "warning",
            "title": "Many Rules Disabled", 
            "message": f"{metrics['disabled_rules']} out of {metrics['total_rules']} rules are disabled",
            "action": "Review and re-enable rules if needed"
        })
    
    if metrics["recent_executions"] == 0 and metrics["enabled_rules"] > 0:
        alerts.append({
            "type": "warning",
            "title": "No Recent Executions",
            "message": "No automation rules have executed in the last 24 hours",
            "action": "Check if rules are configured with appropriate triggers"
        })
    
    if 50 <= metrics["success_rate"] < 80 and metrics["recent_executions"] > 0:
        alerts.append({
            "type": "warning",
            "title": "Moderate Success Rate",
            "message": f"{metrics['success_rate']}% success rate - some rules may need attention",
            "action": "Review execution logs for failed rules"
        })
    
    # Info alerts (positive status)
    if not alerts and metrics["enabled_rules"] > 0:
        alerts.append({
            "type": "success",
            "title": "System Healthy",
            "message": f"All {metrics['enabled_rules']} enabled rules are operating normally",
            "action": "No action needed"
        })
    
    if not alerts and metrics["total_rules"] == 0:
        alerts.append({
            "type": "info",
            "title": "No Rules Configured",
            "message": "No automation rules have been set up yet",
            "action": "Create your first automation rule to get started"
        })
    
    return alerts


def send_failure_alert(rule_name: str, error_details: str) -> None:
    """
    Send an alert for a failed automation execution.
    
    Args:
        rule_name: Name of the failed rule
        error_details: Details of the failure
    """
    logger.warning(f"AUTOMATION FAILURE: Rule '{rule_name}' failed - {error_details}")
    
    # In a real implementation, this could:
    # - Send email notifications
    # - Post to Slack/Discord
    # - Store in a alerts table
    # - Trigger webhooks
    
    # For now, just log the failure
    logger.error(f"Alert sent for failed rule: {rule_name}")


def check_and_alert_on_failures() -> None:
    """
    Check for recent automation failures and send alerts if needed.
    This function can be called periodically to monitor system health.
    """
    try:
        with next(get_db_session()) as db:
            # Check for failures in the last hour
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            
            # Get rules with execution metadata and filter for failures in Python
            # (avoiding SQL LIKE on JSON column)
            recent_rules = db.query(AutomationRule).filter(
                AutomationRule.last_executed >= since,
                AutomationRule.execution_metadata.isnot(None)
            ).all()
            
            for rule in recent_rules:
                try:
                    import json
                    if rule.execution_metadata:
                        if isinstance(rule.execution_metadata, str):
                            metadata = json.loads(rule.execution_metadata)
                        else:
                            metadata = rule.execution_metadata
                        
                        # Only process rules that actually failed
                        if metadata.get("status") == "failed":
                            error_details = metadata.get("error", "Unknown error")
                            send_failure_alert(rule.name, error_details)
                except (json.JSONDecodeError, TypeError, AttributeError):
                    # If we can't parse metadata, consider it a failure
                    send_failure_alert(rule.name, "Error parsing failure details")
                    
    except Exception as e:
        logger.error(f"Error checking for automation failures: {e}") 