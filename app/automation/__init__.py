"""
Automation package for Monzo app.

This package contains the core automation features:
- Pot Sweeps: Move money between pots and accounts
- Autosorter: Intelligent money distribution system
- Auto Topup: Automatically add money to pots
- Pot Manager: Structured pot management without fuzzy name matching
- Rules Management: Database storage and management of automation rules
"""

from .auto_topup import AutoTopup, TopupRule
from .autosorter import (
    Autosorter, 
    AutosorterConfig, 
    PotAllocation,
    TriggerType,
    TimeOfDayTrigger,
    TransactionTrigger,
    DateRangeTrigger
)
from .integration import AutomationIntegration
from .pot_manager import PotCategory, PotManager
from .pot_sweeps import PotSweepRule, PotSweeps
from .rules import AutomationRule, RulesManager

__all__ = [
    "PotSweeps",
    "PotSweepRule",
    "Autosorter",
    "AutosorterConfig",
    "PotAllocation",
    "TriggerType",
    "TimeOfDayTrigger",
    "TransactionTrigger",
    "DateRangeTrigger",
    "AutoTopup",
    "TopupRule",
    "PotManager",
    "PotCategory",
    "RulesManager",
    "AutomationRule",
    "AutomationIntegration",
]
