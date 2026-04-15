"""NebulaGraph schema definitions for the graphrag space."""

SPACE_NAME = "graphrag"

TAG_ENTITY = "entity"
TAG_CHUNK = "chunk"

EDGE_RELATED_TO = "related_to"
EDGE_CONTAINS_CHUNK = "contains_chunk"
EDGE_SAME_AS = "same_as"


TAG_ENTITY_SCHEMA = "CREATE TAG IF NOT EXISTS entity (name string, type string, description string)"
TAG_CHUNK_SCHEMA = "CREATE TAG IF NOT EXISTS chunk (content string, source string, chunk_index int)"

EDGE_RELATED_TO_SCHEMA = "CREATE EDGE IF NOT EXISTS related_to (relation string, weight double)"
EDGE_CONTAINS_CHUNK_SCHEMA = "CREATE EDGE IF NOT EXISTS contains_chunk (position int)"
EDGE_SAME_AS_SCHEMA = "CREATE EDGE IF NOT EXISTS same_as (confidence double)"
