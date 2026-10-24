"""
The fictional organization used by the simulator.

Everything here is synthetic: invented usernames, departments and file paths.
No real people or company data are involved.
"""

import random
from dataclasses import dataclass

# Files and systems that belong to each department, with their sensitivity label.
DEPARTMENT_RESOURCES: dict[str, dict[str, str]] = {
    "Engineering": {
        "repo://eng/web-portal": "INTERNAL",
        "repo://eng/mobile-app": "INTERNAL",
        "repo://eng/payment-service": "CONFIDENTIAL",
        "fs://eng/docs/api_guidelines.pdf": "INTERNAL",
        "fs://eng/docs/system_architecture.pdf": "CONFIDENTIAL",
        "fs://eng/docs/onboarding.md": "PUBLIC",
        "fs://eng/releases/release_notes.md": "PUBLIC",
        "fs://eng/test-data/sample_orders.csv": "INTERNAL",
        "fs://eng/ops/deployment_runbook.md": "INTERNAL",
        "fs://eng/ops/production_credentials_vault.kdbx": "RESTRICTED",
        "fs://eng/security/pentest_report_2026.pdf": "RESTRICTED",
        "fs://eng/design/ui_mockups.fig": "INTERNAL",
    },
    "Finance": {
        "fs://finance/reports/monthly_summary.xlsx": "INTERNAL",
        "fs://finance/reports/q3_forecast.xlsx": "CONFIDENTIAL",
        "fs://finance/invoices/vendor_invoices.xlsx": "CONFIDENTIAL",
        "fs://finance/budget/department_budgets.xlsx": "CONFIDENTIAL",
        "fs://finance/payroll/payroll_2026.xlsx": "RESTRICTED",
        "fs://finance/banking/account_details.xlsx": "RESTRICTED",
        "fs://finance/templates/expense_form.docx": "PUBLIC",
        "fs://finance/policies/travel_policy.pdf": "PUBLIC",
        "fs://finance/audit/audit_checklist.xlsx": "INTERNAL",
        "fs://finance/tax/tax_filings_2025.pdf": "CONFIDENTIAL",
    },
    "Human Resources": {
        "fs://hr/policies/employee_handbook.pdf": "PUBLIC",
        "fs://hr/recruiting/open_positions.xlsx": "INTERNAL",
        "fs://hr/recruiting/candidate_cvs.zip": "CONFIDENTIAL",
        "fs://hr/records/employee_records.xlsx": "RESTRICTED",
        "fs://hr/records/salary_bands.xlsx": "RESTRICTED",
        "fs://hr/reviews/performance_reviews_2026.xlsx": "CONFIDENTIAL",
        "fs://hr/training/training_calendar.xlsx": "INTERNAL",
        "fs://hr/templates/leave_request.docx": "PUBLIC",
        "fs://hr/benefits/insurance_plans.pdf": "INTERNAL",
    },
    "Sales": {
        "crm://sales/leads": "INTERNAL",
        "crm://sales/opportunities": "INTERNAL",
        "fs://sales/pricing/price_list_2026.xlsx": "CONFIDENTIAL",
        "fs://sales/contracts/customer_contracts.zip": "CONFIDENTIAL",
        "fs://sales/presentations/company_deck.pptx": "PUBLIC",
        "fs://sales/reports/weekly_pipeline.xlsx": "INTERNAL",
        "fs://sales/customers/customer_master_list.csv": "RESTRICTED",
        "fs://sales/marketing/brochure.pdf": "PUBLIC",
        "fs://sales/targets/regional_targets.xlsx": "INTERNAL",
    },
    "IT": {
        "fs://it/inventory/asset_inventory.xlsx": "INTERNAL",
        "fs://it/network/network_diagram.vsdx": "CONFIDENTIAL",
        "fs://it/backups/backup_schedule.xlsx": "INTERNAL",
        "fs://it/accounts/admin_accounts.xlsx": "RESTRICTED",
        "fs://it/firewall/firewall_rules.conf": "CONFIDENTIAL",
        "fs://it/helpdesk/ticket_export.csv": "INTERNAL",
        "fs://it/guides/vpn_setup.pdf": "PUBLIC",
        "fs://it/monitoring/server_health.log": "INTERNAL",
        "fs://it/licenses/software_licenses.xlsx": "CONFIDENTIAL",
    },
}

# Resources every employee may use.
SHARED_RESOURCES: dict[str, str] = {
    "fs://company/announcements/newsletter.pdf": "PUBLIC",
    "fs://company/templates/letterhead.docx": "PUBLIC",
    "fs://company/policies/code_of_conduct.pdf": "PUBLIC",
    "fs://company/calendar/holidays_2026.pdf": "PUBLIC",
    "fs://company/projects/shared_roadmap.xlsx": "INTERNAL",
}

APPLICATIONS = ["Outlook", "Teams", "Excel", "Word", "Browser", "VS Code", "ERP", "CRM", "Jira", "PowerPoint"]

# The highest sensitivity each job role normally works with. This describes simulated
# HABITS (what a normal day looks like), not security policy. The security policy
# (which roles are ALLOWED to see what) lives in backend/detection/rule_config.py.
ROLE_HABIT_MAX_SENSITIVITY: dict[str, str] = {
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
}

DEPARTMENT_ROLES: dict[str, list[str]] = {
    "Engineering": ["Software Engineer", "QA Engineer"],
    "Finance": ["Accountant", "Finance Manager"],
    "Human Resources": ["HR Specialist", "HR Manager"],
    "Sales": ["Sales Representative", "Sales Manager"],
    "IT": ["System Administrator", "Night Operations Technician"],
}


@dataclass
class Employee:
    """A simulated employee and the habits the generator uses for them."""

    username: str
    department: str
    job_role: str
    activity_level: float = 1.0  # 1.0 = average amount of work per day
    work_start_hour: int = 8
    night_shift: bool = False  # works roughly 00:30-08:30 instead of office hours


# The fixed list of employees loaded into the demo database (python -m backend.cli seed-demo).
DEMO_EMPLOYEES: list[Employee] = [
    Employee("omar.hassan", "Engineering", "Software Engineer", 1.1, 9),
    Employee("mona.adel", "Engineering", "Software Engineer", 0.9, 8),
    Employee("karim.fathy", "Engineering", "QA Engineer", 1.0, 9),
    Employee("nour.samir", "Engineering", "Software Engineer", 1.2, 10),
    Employee("youssef.tarek", "Engineering", "QA Engineer", 0.8, 8),
    Employee("salma.ibrahim", "Finance", "Accountant", 1.0, 8),
    Employee("hany.mostafa", "Finance", "Accountant", 0.9, 9),
    Employee("dina.khaled", "Finance", "Finance Manager", 0.8, 9),
    Employee("tamer.nabil", "Finance", "Accountant", 1.1, 8),
    Employee("rana.magdy", "Human Resources", "HR Specialist", 1.0, 9),
    Employee("ahmed.saad", "Human Resources", "HR Specialist", 0.9, 8),
    Employee("laila.fouad", "Human Resources", "HR Manager", 0.8, 9),
    Employee("mostafa.ali", "Sales", "Sales Representative", 1.2, 9),
    Employee("heba.yasser", "Sales", "Sales Representative", 1.0, 10),
    Employee("sherif.wael", "Sales", "Sales Manager", 0.9, 9),
    Employee("aya.gamal", "Sales", "Sales Representative", 1.1, 8),
    Employee("ziad.hamdy", "IT", "System Administrator", 1.2, 8),
    Employee("farida.ehab", "IT", "System Administrator", 1.0, 9),
    Employee("khaled.ramy", "IT", "Night Operations Technician", 0.9, 0, night_shift=True),
    Employee("mariam.sobhy", "Engineering", "Software Engineer", 1.0, 9),
    Employee("adham.reda", "Finance", "Accountant", 1.0, 9),
    Employee("nada.osama", "Human Resources", "HR Specialist", 1.1, 8),
    Employee("bassem.lotfy", "Sales", "Sales Manager", 1.0, 9),
    Employee("yara.hesham", "IT", "System Administrator", 0.9, 9),
    Employee("amr.zaki", "Engineering", "QA Engineer", 1.0, 9),
]

# Fridays and Saturdays are the weekend for the simulated organization.
WEEKEND_DAYS = {4, 5}  # Python weekday(): Monday=0 ... Friday=4, Saturday=5


def make_synthetic_population(size: int, rng: random.Random, prefix: str = "train_user") -> list[Employee]:
    """Random employees used only for the AI training dataset (never shown in the app)."""
    population = []
    departments = list(DEPARTMENT_ROLES)
    for index in range(size):
        department = rng.choice(departments)
        role = rng.choice(DEPARTMENT_ROLES[department])
        night_shift = role == "Night Operations Technician"
        population.append(
            Employee(
                username=f"{prefix}_{index:03d}",
                department=department,
                job_role=role,
                activity_level=round(rng.uniform(0.7, 1.3), 2),
                work_start_hour=0 if night_shift else rng.choice([8, 8, 9, 9, 10]),
                night_shift=night_shift,
            )
        )
    return population


def find_demo_employee(username: str) -> Employee | None:
    for employee in DEMO_EMPLOYEES:
        if employee.username == username:
            return employee
    return None
