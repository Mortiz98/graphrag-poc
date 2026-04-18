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

EDGE_REPORTED_BY_SCHEMA = "CREATE EDGE IF NOT EXISTS reported_by (channel string, timestamp string)"

EDGE_OWNS_SCHEMA = "CREATE EDGE IF NOT EXISTS owns (role string, since string)"

EDGE_RESPONSIBLE_FOR_SCHEMA = "CREATE EDGE IF NOT EXISTS responsible_for (role string, since string)"

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
]

ALL_DOMAIN_SCHEMAS = DOMAIN_TAG_SCHEMAS + DOMAIN_EDGE_SCHEMAS


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
