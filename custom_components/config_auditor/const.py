"""Constants for H.A.C.A - v1.0.0."""

DOMAIN = "config_auditor"
NAME = "H.A.C.A"
VERSION = "1.0.0"

# Configuration
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 1440

# Services
SERVICE_SCAN_ALL = "scan_all"
SERVICE_SCAN_AUTOMATIONS = "scan_automations"
SERVICE_SCAN_ENTITIES = "scan_entities"
SERVICE_SCAN_PERFORMANCE = "scan_performance"
SERVICE_GENERATE_REPORT = "generate_report"
SERVICE_LIST_REPORTS = "list_reports"
SERVICE_GET_REPORT_CONTENT = "get_report_content"
SERVICE_FIX_DEVICE_ID = "fix_device_id"
SERVICE_PREVIEW_DEVICE_ID = "preview_device_id"
SERVICE_FIX_MODE = "fix_mode"
SERVICE_PREVIEW_MODE = "preview_mode"
SERVICE_LIST_BACKUPS = "list_backups"
SERVICE_RESTORE_BACKUP = "restore_backup"
SERVICE_PREVIEW_TEMPLATE = "preview_template"
SERVICE_FIX_TEMPLATE = "fix_template"
SERVICE_EXPLAIN_ISSUE = "explain_issue_ai"

# Module Status
MODULE_1_AUTOMATION_SCANNER = True    # ✅ v1.0.0
MODULE_2_HEALTH_MONITOR = True        # ✅ v1.0.0
MODULE_3_PERFORMANCE_ANALYZER = True  # ✅ v1.0.0
MODULE_4_COMPLIANCE_REPORT = True     # ✅ v1.0.0
MODULE_5_REFACTORING_ASSISTANT = True # ✅ v1.0.0
MODULE_6_AI_ASSIST = True             # ✅ v1.0.0
MODULE_7_SECURITY_ANALYZER = True     # ✅ v1.0.0

# Severity levels
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Issue types - Module 1
ISSUE_DEVICE_ID_TRIGGER = "device_id_in_trigger"
ISSUE_DEVICE_ID_ACTION = "device_id_in_action"
ISSUE_TEMPLATE_SIMPLE = "template_condition_simple"
ISSUE_TEMPLATE_NUMERIC = "template_numeric_comparison"
ISSUE_INCORRECT_MODE = "incorrect_mode_for_pattern"
ISSUE_ZOMBIE_REFERENCE = "zombie_entity_reference"

# Issue types - Module 2
ISSUE_UNAVAILABLE = "entity_unavailable"
ISSUE_UNKNOWN_STATE = "entity_unknown_state"
ISSUE_STALE = "entity_stale"
ISSUE_DISABLED_REFERENCED = "disabled_but_referenced"
ISSUE_ZOMBIE_ENTITY = "zombie_entity"
ISSUE_ORPHANED_DEVICE = "orphaned_device_reference"

# Issue types - Module 3
ISSUE_HIGH_FREQUENCY = "high_trigger_frequency"
ISSUE_VERY_HIGH_FREQUENCY = "very_high_trigger_frequency"
ISSUE_BURST_PATTERN = "burst_trigger_pattern"
ISSUE_TEMPLATE_HIGH_REFRESH = "template_high_refresh_rate"

# Paths
BACKUP_DIR = ".haca_backups"
REPORTS_DIR = "haca_reports"
HISTORY_FILE = ".haca_history.json"

# Thresholds
STALE_ENTITY_DAYS = 7
HIGH_FREQUENCY_TRIGGERS_PER_HOUR = 50
VERY_HIGH_FREQUENCY_TRIGGERS_PER_HOUR = 100
BURST_TRIGGERS_IN_MINUTES = 10
BURST_WINDOW_MINUTES = 5
