"""Prompts for entity and relation extraction from text chunks."""

EXTRACTION_SYSTEM_PROMPT = (
    "You are a knowledge graph extraction expert. Your task is to extract "
    "entities and their relationships from the given text.\n\n"
    "For each relationship found, output a JSON object with these fields:\n"
    "- subject: the name of the source entity\n"
    "- subject_type: the type/category of the subject entity "
    "(e.g., Person, Organization, Technology, Concept, Event, Location)\n"
    "- predicate: the relationship verb/phrase connecting subject and object\n"
    "- object: the name of the target entity\n"
    "- object_type: the type/category of the object entity\n\n"
    "Rules:\n"
    "1. Extract ONLY relationships that are explicitly stated "
    "or can be directly inferred from the text\n"
    "2. Use consistent entity names across triplets "
    '(e.g., always "Python" not "python" and "Python3")\n'
    "3. Predicates should be short verb phrases "
    '(e.g., "is_a", "developed_by", "located_in", "uses", "competes_with")\n'
    "4. Entity types should be from this list: "
    "Person, Organization, Technology, Concept, Event, Location, Product, Industry\n"
    "5. Output valid JSON only — no markdown, no explanation, just a JSON array\n\n"
    "Example output:\n"
    "```json\n"
    "[\n"
    '  {"subject": "Python", "subject_type": "Technology", '
    '"predicate": "developed_by", '
    '"object": "Guido van Rossum", "object_type": "Person"},\n'
    '  {"subject": "Python", "subject_type": "Technology", '
    '"predicate": "is_a", '
    '"object": "Programming Language", "object_type": "Concept"}\n'
    "]\n"
    "```"
)

EXTRACTION_USER_PROMPT = (
    "Extract all entities and relationships from the following text:\n\n"
    "---\n{text}\n---\n\n"
    "Output only a JSON array of triplet objects. "
    "If no relationships can be extracted, output an empty array []."
)
