"""Structured output parsing with validation.

Implements the structured output escalation ladder (section 5.6):
1. response_format: json_schema (if supported)
2. response_format: json_object + schema in prompt
3. Function calling / tool with schema
4. Guided decoding (if engine supports)
5. Parse with repair (max 2 attempts)

Never produces a silent default value - failures are loud.
"""

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(Exception):
    """Failed to parse structured output after all attempts."""

    pass


class StructuredOutputParser:
    """Parse LLM output into validated Pydantic models."""

    def __init__(self, max_repair_attempts: int = 2):
        self.max_repair_attempts = max_repair_attempts

    def parse(self, content: str, model: type[T]) -> T:
        """Parse JSON content into a Pydantic model.

        Raises StructuredOutputError on failure - never returns a default.
        """
        # Try direct parse
        try:
            data = json.loads(content)
            return model.model_validate(data)
        except json.JSONDecodeError as e:
            # Try to extract JSON from markdown code blocks
            extracted = self._extract_json_block(content)
            if extracted:
                try:
                    data = json.loads(extracted)
                    return model.model_validate(data)
                except (json.JSONDecodeError, ValidationError):
                    pass
            raise StructuredOutputError(f"Failed to parse JSON: {e}") from e
        except ValidationError as e:
            raise StructuredOutputError(f"Validation failed: {e}") from e

    def _extract_json_block(self, content: str) -> str | None:
        """Extract JSON from markdown code blocks."""
        # Look for ```json ... ``` blocks
        start_markers = ["```json", "```"]
        end_marker = "```"

        for marker in start_markers:
            if marker in content:
                start = content.find(marker) + len(marker)
                end = content.find(end_marker, start)
                if end > start:
                    return content[start:end].strip()

        return None

    def build_json_schema_format(self, model: type[BaseModel]) -> dict[str, object]:
        """Build response_format for json_schema mode."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": model.__name__,
                "schema": model.model_json_schema(),
                "strict": True,
            },
        }

    def build_json_object_format(self) -> dict[str, str]:
        """Build response_format for json_object mode."""
        return {"type": "json_object"}

    def build_schema_prompt(self, model: type[BaseModel]) -> str:
        """Build a prompt snippet describing the expected JSON schema."""
        schema = model.model_json_schema()
        return f"""
Respond with valid JSON matching this schema:

```json
{json.dumps(schema, indent=2)}
```

Do not include any text outside the JSON object.
"""
