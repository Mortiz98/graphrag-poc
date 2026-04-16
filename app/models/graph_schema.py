SPACE_NAME = "graphrag"

TAG_ENTITY = "entity"

EDGE_RELATED_TO = "related_to"

TAG_ENTITY_SCHEMA = "CREATE TAG IF NOT EXISTS entity (name string, type string, description string)"

EDGE_RELATED_TO_SCHEMA = "CREATE EDGE IF NOT EXISTS related_to (relation string, weight double)"


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
