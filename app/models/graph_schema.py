SPACE_NAME = "graphrag"

TAG_ENTITY = "entity"

EDGE_RELATED_TO = "related_to"

TAG_ENTITY_SCHEMA = "CREATE TAG IF NOT EXISTS entity (name string, type string, description string)"

EDGE_RELATED_TO_SCHEMA = "CREATE EDGE IF NOT EXISTS related_to (relation string, weight double)"
