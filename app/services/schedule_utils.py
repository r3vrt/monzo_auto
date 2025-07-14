import re
from typing import Any, Dict, Optional
from app.services.database_service import db_service

def cron_to_human(cron: str) -> str:
    if not cron or not cron.strip():
        return "No schedule set"
    parts = cron.strip().split()
    if len(parts) != 5:
        return "Invalid cron format"
    minute, hour, dom, month, dow = parts
    # Every X minutes
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        interval = minute[2:]
        return f"Every {interval} minutes"
    # Every day at specific hour
    if minute == "0" and hour != "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every day at {hour.zfill(2)}:00"
    # Every weekday at specific hour
    if minute == "0" and hour != "*" and dom == "*" and month == "*" and dow in ["1", "2", "3", "4", "5", "6", "0"]:
        weekday = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][int(dow)%7]
        return f"Every {weekday} at {hour.zfill(2)}:00"
    # At specific day of month and hour
    if minute == "0" and hour != "*" and dom != "*" and month == "*" and dow == "*":
        return f"At {hour.zfill(2)}:00 on the {dom}{'st' if dom=='1' else 'th'} of each month"
    # At specific day of month, hour, and minute
    if minute != "*" and hour != "*" and dom != "*" and month == "*" and dow == "*":
        return f"At {hour.zfill(2)}:{minute.zfill(2)} on the {dom}{'st' if dom=='1' else 'th'} of each month"
    # At midnight on the 1st of each month
    if minute == "0" and hour == "0" and dom == "1" and month == "*" and dow == "*":
        return "At midnight on the 1st of each month"
    # Every day at midnight
    if minute == "0" and hour == "0" and dom == "*" and month == "*" and dow == "*":
        return "Every day at midnight"
    # Fallback for custom patterns
    return f"At {hour.zfill(2)}:{minute.zfill(2)} on day {dom} of month {month} (weekday {dow})"

def schedule_to_human(schedule: Any) -> str:
    # Handle legacy cron string
    if isinstance(schedule, str):
        return cron_to_human(schedule)
    if not schedule or not schedule.get("type") or schedule["type"] == "none":
        return "No schedule set"
    t = schedule["type"]
    if t == "interval":
        n = schedule.get("minutes") or schedule.get("hours")
        unit = "minutes" if schedule.get("minutes") else "hours"
        return f"Every {n} {unit}" if n else "Interval schedule"
    if t == "daily":
        h = int(schedule.get("hour", 0))
        m = int(schedule.get("minute", 0))
        return f"Every day at {h:02d}:{m:02d}"
    if t == "weekly":
        h = int(schedule.get("hour", 0))
        m = int(schedule.get("minute", 0))
        dow = schedule.get("day_of_week", "0")
        weekday = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][int(dow)%7]
        return f"Every {weekday} at {h:02d}:{m:02d}"
    if t == "monthly":
        h = int(schedule.get("hour", 0))
        m = int(schedule.get("minute", 0))
        dom = int(schedule.get("day", 1))
        return f"On the {dom} at {h:02d}:{m:02d} each month"
    if t == "custom":
        return f"Custom: {schedule.get('cron', '')}"
    return "Unknown schedule"

def schedule_form_to_struct(pattern, hour, minute, weekday, dom, x_minutes, custom_cron):
    if pattern == "none":
        return {"type": "none"}
    if pattern == "every_x_minutes" and x_minutes:
        return {"type": "interval", "minutes": int(x_minutes)}
    if pattern == "daily":
        return {"type": "daily", "hour": int(hour), "minute": int(minute)}
    if pattern == "weekly":
        return {"type": "weekly", "hour": int(hour), "minute": int(minute), "day_of_week": int(weekday)}
    if pattern == "monthly":
        return {"type": "monthly", "hour": int(hour), "minute": int(minute), "day": int(dom)}
    if pattern == "custom" and custom_cron:
        return {"type": "custom", "cron": custom_cron.strip()}
    return {"type": "none"}

def schedule_struct_to_trigger(schedule):
    """Convert schedule struct to APScheduler trigger args."""
    if not schedule or schedule.get("type") == "none":
        return None, None
    t = schedule["type"]
    if t == "interval":
        return "interval", {"minutes": schedule["minutes"]}
    if t == "daily":
        return "cron", {"hour": schedule["hour"], "minute": schedule["minute"]}
    if t == "weekly":
        return "cron", {"day_of_week": schedule["day_of_week"], "hour": schedule["hour"], "minute": schedule["minute"]}
    if t == "monthly":
        return "cron", {"day": schedule["day"], "hour": schedule["hour"], "minute": schedule["minute"]}
    if t == "custom":
        # Parse cron string to dict (inline, not using parse_cron)
        cron_str = schedule.get("cron", "")
        fields = cron_str.strip().split()
        if len(fields) != 5:
            return None, None
        return "cron", {
            "minute": fields[0],
            "hour": fields[1],
            "day": fields[2],
            "month": fields[3],
            "day_of_week": fields[4],
        }
    return None, None

def migrate_legacy_cron_schedules():
    """Migrate any legacy cron string schedules in automation_tasks to the new structured format. Must be called within a Flask app context."""
    automation_config = db_service.get_setting("general.automation_tasks", {})
    changed = False
    for task in ["auto_topup", "sweep_pots", "autosorter", "combined"]:
        task_conf = automation_config.get(task, {})
        sched = task_conf.get("schedule")
        # If it's a string and looks like a cron pattern, migrate
        if isinstance(sched, str) and re.match(r"^([\d\*/]+\s+){4}[\d\*/]+$", sched.strip()):
            # Convert to new format as custom
            task_conf["schedule"] = {"type": "custom", "cron": sched.strip()}
            automation_config[task] = task_conf
            changed = True
    if changed:
        db_service.save_setting("general.automation_tasks", automation_config, data_type="json") 