SPACE_NAME = "graphrag"

TAG_ENTITY = "entity"
TAG_ISSUE = "issue"
TAG_STAKEHOLDER = "stakeholder"
TAG_COMMITMENT = "commitment"

EDGE_RELATED_TO = "related_to"
EDGE_HAS_SYMPTOM = "has_symptom"
EDGE_CAUSED_BY = "caused_by"
EDGE_RESOLVED_BY = "resolved_by"
EDGE_AFFECTS = "affects"
EDGE_ESCALATED_TO = "escalated_to"
EDGE_GOVERNED_BY = "governed_by"
EDGE_REPORTED_BY = "reported_by"
EDGE_OWNS = "owns"
EDGE_RESPONSIBLE_FOR = "responsible_for"
EDGE_AFFECTS_VERSION = "affects_version"
EDGE_DOCUMENTED_IN = "documented_in"
EDGE_DEPENDS_ON = "depends_on"
EDGE_IS_A = "is_a"
EDGE_HAS_COMPONENT = "has_component"
EDGE_PRODUCES_ERROR = "produces_error"

TAG_ENTITY_SCHEMA = "CREATE TAG IF NOT EXISTS entity (name string, type string, description string)"

TAG_ISSUE_SCHEMA = (
    "CREATE TAG IF NOT EXISTS issue ("
    "name string, "
    "severity string, "
    "status string, "
    "product string, "
    "version string, "
    "channel string, "
    "description string)"
)

TAG_STAKEHOLDER_SCHEMA = (
    "CREATE TAG IF NOT EXISTS stakeholder ("
    "name string, "
    "role string, "
    "account_id string, "
    "email string, "
    "description string)"
)

TAG_COMMITMENT_SCHEMA = (
    "CREATE TAG IF NOT EXISTS commitment ("
    "name string, "
    "account_id string, "
    "due_date string, "
    "status string, "
    "description string)"
)

EDGE_RELATED_TO_SCHEMA = "CREATE EDGE IF NOT EXISTS related_to (relation string, weight double)"

EDGE_HAS_SYMPTOM_SCHEMA = "CREATE EDGE IF NOT EXISTS has_symptom (context string)"

EDGE_CAUSED_BY_SCHEMA = "CREATE EDGE IF NOT EXISTS caused_by (confidence double)"

EDGE_RESOLVED_BY_SCHEMA = "CREATE EDGE IF NOT EXISTS resolved_by (step_order int, outcome string)"

EDGE_AFFECTS_SCHEMA = "CREATE EDGE IF NOT EXISTS affects (scope string)"

EDGE_ESCALATED_TO_SCHEMA = "CREATE EDGE IF NOT EXISTS escalated_to (reason string, priority string)"

EDGE_GOVERNED_BY_SCHEMA = "CREATE EDGE IF NOT EXISTS governed_by (policy_type string)"

EDGE_REPORTED_BY_SCHEMA = "CREATE EDGE IF NOT EXISTS reported_by (channel string, reported_at string)"

EDGE_OWNS_SCHEMA = "CREATE EDGE IF NOT EXISTS owns (role string, since string)"

EDGE_RESPONSIBLE_FOR_SCHEMA = "CREATE EDGE IF NOT EXISTS responsible_for (role string, since string)"

EDGE_AFFECTS_VERSION_SCHEMA = "CREATE EDGE IF NOT EXISTS affects_version (version string)"

EDGE_DOCUMENTED_IN_SCHEMA = "CREATE EDGE IF NOT EXISTS documented_in (section string)"

EDGE_DEPENDS_ON_SCHEMA = "CREATE EDGE IF NOT EXISTS depends_on (context string)"

EDGE_IS_A_SCHEMA = "CREATE EDGE IF NOT EXISTS is_a (category string)"

EDGE_HAS_COMPONENT_SCHEMA = "CREATE EDGE IF NOT EXISTS has_component (scope string)"

EDGE_PRODUCES_ERROR_SCHEMA = "CREATE EDGE IF NOT EXISTS produces_error (frequency string)"

DOMAIN_TAG_SCHEMAS = [
    TAG_ENTITY_SCHEMA,
    TAG_ISSUE_SCHEMA,
    TAG_STAKEHOLDER_SCHEMA,
    TAG_COMMITMENT_SCHEMA,
]

DOMAIN_EDGE_SCHEMAS = [
    EDGE_RELATED_TO_SCHEMA,
    EDGE_HAS_SYMPTOM_SCHEMA,
    EDGE_CAUSED_BY_SCHEMA,
    EDGE_RESOLVED_BY_SCHEMA,
    EDGE_AFFECTS_SCHEMA,
    EDGE_ESCALATED_TO_SCHEMA,
    EDGE_GOVERNED_BY_SCHEMA,
    EDGE_REPORTED_BY_SCHEMA,
    EDGE_OWNS_SCHEMA,
    EDGE_RESPONSIBLE_FOR_SCHEMA,
    EDGE_AFFECTS_VERSION_SCHEMA,
    EDGE_DOCUMENTED_IN_SCHEMA,
    EDGE_DEPENDS_ON_SCHEMA,
    EDGE_IS_A_SCHEMA,
    EDGE_HAS_COMPONENT_SCHEMA,
    EDGE_PRODUCES_ERROR_SCHEMA,
]

ALL_DOMAIN_SCHEMAS = DOMAIN_TAG_SCHEMAS + DOMAIN_EDGE_SCHEMAS

ALL_EDGE_NAMES = [
    EDGE_RELATED_TO,
    EDGE_HAS_SYMPTOM,
    EDGE_CAUSED_BY,
    EDGE_RESOLVED_BY,
    EDGE_AFFECTS,
    EDGE_ESCALATED_TO,
    EDGE_GOVERNED_BY,
    EDGE_REPORTED_BY,
    EDGE_OWNS,
    EDGE_RESPONSIBLE_FOR,
    EDGE_AFFECTS_VERSION,
    EDGE_DOCUMENTED_IN,
    EDGE_DEPENDS_ON,
    EDGE_IS_A,
    EDGE_HAS_COMPONENT,
    EDGE_PRODUCES_ERROR,
]

ENTITY_TYPE_TO_TAG = {
    "Issue": TAG_ISSUE,
    "Person": TAG_ENTITY,
    "User": TAG_ENTITY,
    "Technology": TAG_ENTITY,
    "Product": TAG_ENTITY,
    "Symptom": TAG_ENTITY,
    "RootCause": TAG_ENTITY,
    "Fix": TAG_ENTITY,
    "ErrorCode": TAG_ENTITY,
    "Version": TAG_ENTITY,
    "Component": TAG_ENTITY,
    "Team": TAG_ENTITY,
    "Policy": TAG_ENTITY,
    "EscalationPath": TAG_ENTITY,
    "Playbook": TAG_ENTITY,
    "Channel": TAG_ENTITY,
    "Severity": TAG_ENTITY,
    "entity": TAG_ENTITY,
}

PREDICATE_TO_EDGE = {
    "has_symptom": EDGE_HAS_SYMPTOM,
    "caused_by": EDGE_CAUSED_BY,
    "resolved_by": EDGE_RESOLVED_BY,
    "affects": EDGE_AFFECTS,
    "affects_version": EDGE_AFFECTS_VERSION,
    "escalated_to": EDGE_ESCALATED_TO,
    "governed_by": EDGE_GOVERNED_BY,
    "reported_by": EDGE_REPORTED_BY,
    "documented_in": EDGE_DOCUMENTED_IN,
    "depends_on": EDGE_DEPENDS_ON,
    "is_a": EDGE_IS_A,
    "has_component": EDGE_HAS_COMPONENT,
    "produces_error": EDGE_PRODUCES_ERROR,
    "owns": EDGE_OWNS,
    "responsible_for": EDGE_RESPONSIBLE_FOR,
}


EDGE_DEFAULT_PROPS = {
    EDGE_HAS_SYMPTOM: ("context",),
    EDGE_CAUSED_BY: ("confidence",),
    EDGE_RESOLVED_BY: ("step_order", "outcome"),
    EDGE_AFFECTS: ("scope",),
    EDGE_ESCALATED_TO: ("reason", "priority"),
    EDGE_GOVERNED_BY: ("policy_type",),
    EDGE_REPORTED_BY: ("channel", "timestamp"),
    EDGE_OWNS: ("role", "since"),
    EDGE_RESPONSIBLE_FOR: ("role", "since"),
    EDGE_AFFECTS_VERSION: ("version",),
    EDGE_DOCUMENTED_IN: ("section",),
    EDGE_DEPENDS_ON: ("context",),
    EDGE_IS_A: ("category",),
    EDGE_HAS_COMPONENT: ("scope",),
    EDGE_PRODUCES_ERROR: ("frequency",),
}

TAG_INSERT_PROPS = {
    TAG_ENTITY: ("name", "type", "description"),
    TAG_ISSUE: ("name", "severity", "status", "product", "version", "channel", "description"),
    TAG_STAKEHOLDER: ("name", "role", "account_id", "email", "description"),
    TAG_COMMITMENT: ("name", "account_id", "due_date", "status", "description"),
}


def escape_ngql(value: str) -> str:
    """Escape a string value for safe insertion into nGQL queries.

    Prevents injection by escaping characters that could break out of
    string literals in nGQL statements (double quotes, backslashes,
    single quotes, and control characters).
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
