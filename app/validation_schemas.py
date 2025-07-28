"""
Input validation schemas for API endpoints using marshmallow.
These schemas prevent injection attacks and ensure data integrity.
"""

from marshmallow import Schema, fields, validate, ValidationError
from typing import Dict, Any, Optional
import re


class AccountSelectSchema(Schema):
    """Schema for account selection endpoint"""
    account_ids = fields.List(
        fields.String(validate=validate.Length(min=1, max=100)), 
        required=True,
        validate=validate.Length(min=1, max=50)  # Reasonable limit
    )
    account_names = fields.Dict(
        keys=fields.String(validate=validate.Length(min=1, max=100)),
        values=fields.String(validate=validate.Length(min=0, max=200)),
        required=False,
        allow_none=True
    )


class AutomationRuleCreateSchema(Schema):
    """Schema for creating automation rules"""
    name = fields.String(
        required=True,
        validate=validate.Length(min=1, max=200)
    )
    rule_type = fields.String(
        required=True,
        validate=validate.OneOf(['pot_sweep', 'autosorter', 'auto_topup', 'bills_pot_logic'])
    )
    config = fields.Dict(required=True)
    enabled = fields.Boolean(required=False, allow_none=True)


class AutomationRuleUpdateSchema(Schema):
    """Schema for updating automation rules"""
    name = fields.String(
        required=False,
        validate=validate.Length(min=1, max=200)
    )
    config = fields.Dict(required=False)
    enabled = fields.Boolean(required=False)


class PotTransferSchema(Schema):
    """Schema for pot deposit/withdraw operations"""
    amount = fields.Integer(
        required=True,
        validate=validate.Range(min=1, max=100000000)  # £1 to £1M in pence
    )
    dedupe_id = fields.String(
        required=False,
        validate=validate.Length(min=1, max=100)
    )


class UserPotCategorySchema(Schema):
    """Schema for user pot category updates"""
    pot_id = fields.String(
        required=True,
        validate=validate.Length(min=1, max=100)
    )
    category = fields.String(
        required=True,
        validate=validate.OneOf(['priority', 'goal', 'investment', 'bills', 'holding'])
    )


class MonzoCredentialsSchema(Schema):
    """Schema for Monzo API credentials"""
    client_id = fields.String(
        required=True,
        validate=validate.Length(min=1, max=200)
    )
    client_secret = fields.String(
        required=True,
        validate=validate.Length(min=1, max=200)
    )
    redirect_uri = fields.String(
        required=True,
        validate=validate.Length(min=1, max=500)
    )


class LoggingConfigSchema(Schema):
    """Schema for logging configuration"""
    level = fields.String(
        required=True,
        validate=validate.OneOf(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    )
    logger_name = fields.String(
        required=False,
        validate=validate.Length(min=1, max=100)
    )


def validate_request_json(schema_class: type, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate request JSON data against a marshmallow schema.
    
    Args:
        schema_class: The marshmallow schema class to use for validation
        data: The JSON data to validate
        
    Returns:
        Validated and cleaned data
        
    Raises:
        ValidationError: If validation fails
    """
    if data is None:
        raise ValidationError("No JSON data provided")
    
    schema = schema_class()
    try:
        validated_data = schema.load(data)
        
        # Handle default values for compatibility
        if schema_class == AccountSelectSchema:
            if 'account_names' not in validated_data or validated_data['account_names'] is None:
                validated_data['account_names'] = {}
        elif schema_class == AutomationRuleCreateSchema:
            if 'enabled' not in validated_data or validated_data['enabled'] is None:
                validated_data['enabled'] = True
                
        return validated_data
    except ValidationError as e:
        # Log the validation error for security monitoring
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Input validation failed: {e.messages}")
        raise e


def create_validation_error_response(error: ValidationError) -> tuple:
    """
    Create a standardized error response for validation failures.
    
    Args:
        error: The ValidationError instance
        
    Returns:
        Tuple of (response_dict, status_code)
    """
    return {
        "error": "Invalid input data",
        "validation_errors": error.messages,
        "message": "Please check your input and try again"
    }, 400 