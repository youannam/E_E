"""
Default configuration of the cybersecurity rules.

These values are copied into the `rule_settings` table when the database is initialized.
After that, an administrator can change them through the API (PATCH /api/v1/rules/{rule_id})
or the web dashboard's Rules page, without editing code.

Why most thresholds look like  max(minimum, mean + k * std):
    Different employees have different normal workloads, so one fixed number would be
    too strict for busy people and too loose for quiet people. Each count is compared with
    the user's OWN history (mean and standard deviation). The minimum stops the rule from
    firing on tiny numbers when someone's history is almost always zero.
"""

DEFAULT_RULE_SETTINGS: dict[str, dict] = {
    "UNUSUAL_LOGIN_TIME": {
        "weight": 15,
        "parameters": {
            # If the user logs in at night less often than this on an average day, a night login is unusual.
            "max_usual_night_logins_per_day": 0.2,
        },
    },
    "EXCESSIVE_DOWNLOADS": {
        "weight": 20,
        "parameters": {"std_multiplier": 3, "minimum_count": 15},
    },
    "EXCESSIVE_DOWNLOAD_VOLUME": {
        "weight": 20,
        "parameters": {"std_multiplier": 3, "minimum_mb": 150},
    },
    "SENSITIVE_RESOURCE_ACCESS": {
        "weight": 25,
        "parameters": {
            # Highest sensitivity each job role is ALLOWED to access (organization policy).
            "role_clearance": {
                "Software Engineer": "CONFIDENTIAL",
                "QA Engineer": "INTERNAL",
                "Accountant": "CONFIDENTIAL",
                "Finance Manager": "RESTRICTED",
                "HR Specialist": "CONFIDENTIAL",
                "HR Manager": "RESTRICTED",
                "Sales Representative": "INTERNAL",
                "Sales Manager": "CONFIDENTIAL",
                "System Administrator": "CONFIDENTIAL",
                "Night Operations Technician": "INTERNAL",
            },
            # Used for job roles that are not listed above.
            "default_clearance": "INTERNAL",
        },
    },
    "MASS_FILE_DELETION": {
        "weight": 20,
        "parameters": {"std_multiplier": 3, "minimum_count": 20},
    },
    "USB_SENSITIVE_TRANSFER": {
        "weight": 30,
        "parameters": {"minimum_transfers": 1},
    },
    "UNUSUAL_RESOURCE_ACCESS": {
        "weight": 10,
        "parameters": {"minimum_new_resources": 5},
    },
    "HIGH_ACTIVITY_VOLUME": {
        "weight": 10,
        "parameters": {"std_multiplier": 3, "minimum_events": 120},
    },
}

# Fallback "normal day" used when neither the user nor their department has enough history.
# These numbers describe an average simulated office day (see simulator/generator.py) and
# are deliberately generous, so a brand-new user is not flagged just for being new.
DEFAULT_BASELINE_MEANS: dict[str, float] = {
    "total_events": 45, "login_count": 1.3, "night_login_count": 0, "night_event_count": 0,
    "unique_active_hours": 9, "file_access_count": 16, "sensitive_access_count": 3,
    "download_count": 3, "download_mb": 8, "upload_count": 2, "delete_count": 1,
    "usb_event_count": 0.1, "usb_sensitive_transfer_count": 0, "email_count": 10, "unique_resources": 8,
}
DEFAULT_BASELINE_STDS: dict[str, float] = {
    "total_events": 10, "login_count": 0.5, "night_login_count": 0.1, "night_event_count": 0.5,
    "unique_active_hours": 1.5, "file_access_count": 5, "sensitive_access_count": 3,
    "download_count": 2, "download_mb": 8, "upload_count": 1.5, "delete_count": 1,
    "usb_event_count": 0.4, "usb_sensitive_transfer_count": 0.1, "email_count": 3.5, "unique_resources": 3,
}

# Baseline settings (see backend/detection/baseline.py).
BASELINE_HISTORY_DAYS = 30       # look back at most this many days
MIN_INDIVIDUAL_DAYS = 7          # active days needed before the user's own history is trusted
MIN_PEER_USER_DAYS = 20          # user-days needed from the department for a peer-group baseline
