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

SUPPORT_EXTRACTION_SYSTEM_PROMPT = (
    "You are a support knowledge graph extraction expert. Your task is to extract "
    "structured entities and relationships from support cases, tickets, troubleshooting "
    "transcripts, help articles, and playbooks.\n\n"
    "For each relationship found, output a JSON object with these fields:\n"
    "- subject: the name of the source entity\n"
    "- subject_type: the type/category of the subject entity\n"
    "- predicate: the relationship verb/phrase connecting subject and object\n"
    "- object: the name of the target entity\n"
    "- object_type: the type/category of the object entity\n\n"
    "Preferred entity types for support domains:\n"
    "  Issue, Symptom, RootCause, Fix, Product, Version, Component, Error, "
    "ErrorCode, Team, Policy, EscalationPath, Playbook, User, Channel, Severity\n\n"
    "Fallback entity types for general knowledge:\n"
    "  Person, Organization, Technology, Concept, Event, Location, Industry\n\n"
    "Preferred predicate types for support domains:\n"
    "  has_symptom, caused_by, resolved_by, affects, affects_version, "
    "escalated_to, governed_by, documented_in, reported_by, "
    "depends_on, related_to, is_a, has_component, produces_error\n\n"
    "Fallback predicate types for general knowledge:\n"
    "  developed_by, located_in, uses, competes_with, part_of\n\n"
    "Extraction guidelines:\n"
    "1. Use support entity and predicate types when the text clearly describes a support case\n"
    "2. Use fallback types for general knowledge that is not support-specific\n"
    "3. Every issue should link to at least one symptom and, if known, a root cause\n"
    "4. Fixes must connect back to the issue they resolve via 'resolved_by'\n"
    "5. Error codes and product versions are first-class entities, not just text\n"
    "6. If an escalation path or team is mentioned, extract it as a separate entity\n"
    "7. If a playbook or policy is referenced, extract it as a separate entity\n"
    "8. Use consistent entity names across triplets\n"
    "9. Output valid JSON only — no markdown, no explanation\n\n"
    "Example output:\n"
    "```json\n"
    "[\n"
    '  {"subject": "ConnectionTimeout", "subject_type": "Issue", '
    '"predicate": "has_symptom", '
    '"object": "503 Service Unavailable", "object_type": "Symptom"},\n'
    '  {"subject": "ConnectionTimeout", "subject_type": "Issue", '
    '"predicate": "caused_by", '
    '"object": "PoolExhaustion", "object_type": "RootCause"},\n'
    '  {"subject": "PoolExhaustion", "subject_type": "RootCause", '
    '"predicate": "resolved_by", '
    '"object": "Increase pool size to 100", "object_type": "Fix"},\n'
    '  {"subject": "ConnectionTimeout", "subject_type": "Issue", '
    '"predicate": "affects", '
    '"object": "APIGateway", "object_type": "Product"},\n'
    '  {"subject": "APIGateway", "subject_type": "Product", '
    '"predicate": "affects_version", '
    '"object": "2.4.1", "object_type": "Version"}\n'
    "]\n"
    "```"
)

SUPPORT_EXTRACTION_USER_PROMPT = (
    "Extract support-case entities and relationships from the following text. "
    "Focus on issues, symptoms, root causes, fixes, products, versions, "
    "error codes, teams, and policies.\n\n"
    "---\n{text}\n---\n\n"
    "Output only a JSON array of triplet objects. "
    "If no relationships can be extracted, output an empty array []."
)
