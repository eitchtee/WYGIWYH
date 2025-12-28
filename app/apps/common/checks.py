"""
Django System Checks for required environment variables.

This module validates that required environment variables (those without defaults)
are present before the application starts.
"""

import os

from django.core.checks import Error, register


# List of environment variables that are required (no default values)
# Based on the README.md documentation
REQUIRED_ENV_VARS = [
    ("SECRET_KEY", "This is used to provide cryptographic signing."),
    ("SQL_DATABASE", "The name of your postgres database."),
]

# List of environment variables that must be valid integers if set
INT_ENV_VARS = [
    ("TASK_WORKERS", "How many workers to have for async tasks."),
    ("SESSION_EXPIRY_TIME", "The age of session cookies, in seconds."),
    ("INTERNAL_PORT", "The port on which the app listens on."),
    ("DJANGO_VITE_DEV_SERVER_PORT", "The port where Vite's dev server is running"),
]


@register()
def check_required_env_vars(app_configs, **kwargs):
    """
    Check that all required environment variables are set.

    Returns a list of Error objects for any missing required variables.
    """
    errors = []

    for var_name, description in REQUIRED_ENV_VARS:
        value = os.getenv(var_name)
        if not value:
            errors.append(
                Error(
                    f"Required environment variable '{var_name}' is not set.",
                    hint=f"{description} Please set this variable in your .env file or environment.",
                    id="wygiwyh.E001",
                )
            )

    return errors


@register()
def check_int_env_vars(app_configs, **kwargs):
    """
    Check that environment variables that should be integers are valid.

    Returns a list of Error objects for any invalid integer variables.
    """
    errors = []

    for var_name, description in INT_ENV_VARS:
        value = os.getenv(var_name)
        if value is not None:
            try:
                int(value)
            except ValueError:
                errors.append(
                    Error(
                        f"Environment variable '{var_name}' must be a valid integer, got '{value}'.",
                        hint=f"{description}",
                        id="wygiwyh.E002",
                    )
                )

    return errors


@register()
def check_soft_delete_config(app_configs, **kwargs):
    """
    Check that KEEP_DELETED_TRANSACTIONS_FOR is a valid integer when ENABLE_SOFT_DELETE is enabled.

    Returns a list of Error objects if the configuration is invalid.
    """
    errors = []

    enable_soft_delete = os.getenv("ENABLE_SOFT_DELETE", "false").lower() == "true"

    if enable_soft_delete:
        keep_deleted_for = os.getenv("KEEP_DELETED_TRANSACTIONS_FOR")
        if keep_deleted_for is not None:
            try:
                int(keep_deleted_for)
            except ValueError:
                errors.append(
                    Error(
                        f"Environment variable 'KEEP_DELETED_TRANSACTIONS_FOR' must be a valid integer when ENABLE_SOFT_DELETE is enabled, got '{keep_deleted_for}'.",
                        hint="Time in days to keep soft deleted transactions for. Set to 0 to keep all transactions indefinitely.",
                        id="wygiwyh.E003",
                    )
                )

    return errors
