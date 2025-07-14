"""Monitoring service for business logic related to system monitoring."""

from typing import Any, Dict

from app.services.monzo_service import MonzoService
from app.services.metrics_service import metrics_service
import time


def get_system_status() -> Dict[str, Any]:
    """Get system status and metrics, including Monzo API connectivity and account count.

    Returns:
        Dict[str, Any]: System status data for rendering.
    """
    monzo_status = "disconnected"
    account_count = 0
    try:
        monzo_service = MonzoService()
        if monzo_service.client:
            accounts = monzo_service.get_accounts()
            monzo_status = "connected"
            account_count = len(accounts)
    except Exception:
        pass
    metrics = metrics_service.get_metrics()
    return {
        "api_status": monzo_status,
        "account_count": account_count,
        "active_tasks": 4,
        "errors": sum(m.get("failures") or 0 for m in metrics.values()),
        "last_sync": "2024-01-01T00:00:00Z",
        "task_metrics": metrics,
    }


def get_monzo_status() -> Dict[str, Any]:
    """Get detailed Monzo API status, including connectivity and account info.

    Returns:
        Dict[str, Any]: Monzo API status data for rendering.
    """
    try:
        monzo_service = MonzoService()
        if not monzo_service.client:
            return {
                "status": "not_configured",
                "message": "OAuth client not configured",
                "client_configured": False,
                "accounts_found": 0,
            }
        accounts = monzo_service.get_accounts()
        return {
            "status": "connected",
            "accounts_found": len(accounts),
            "client_configured": True,
            "message": "Successfully connected to Monzo API",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Connection failed: {str(e)}",
            "client_configured": True,
            "accounts_found": 0,
        }


def get_health_status() -> Dict[str, Any]:
    """Get health status for the API or system.

    Returns:
        Dict[str, Any]: Health status data for rendering or API.
    """
    return {"status": "healthy", "service": "monzo-automation", "version": "1.0.0"}


def get_metrics_prometheus() -> str:
    """Return Prometheus-style metrics as a string."""
    metrics = metrics_service.get_metrics()
    lines = []
    now = int(time.time())
    for task, m in metrics.items():
        executions = m.get('executions') or 0
        failures = m.get('failures') or 0
        last_duration = m.get('last_duration') or 0.0
        total_duration = m.get('total_duration') or 0.0
        lines.append(f"task_executions_total{{task=\"{task}\"}} {executions}")
        lines.append(f"task_failures_total{{task=\"{task}\"}} {failures}")
        lines.append(f"task_last_duration_seconds{{task=\"{task}\"}} {last_duration}")
        avg_duration = (total_duration / executions) if executions else 0.0
        lines.append(f"task_avg_duration_seconds{{task=\"{task}\"}} {avg_duration}")
        if m.get('last_success'):
            lines.append(f"task_last_success_timestamp{{task=\"{task}\"}} {int(m.get('last_success') or 0)}")
        if m.get('last_failure'):
            lines.append(f"task_last_failure_timestamp{{task=\"{task}\"}} {int(m.get('last_failure') or 0)}")
    return "\n".join(lines)
