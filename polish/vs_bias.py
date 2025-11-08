"""
VS Bias Prompt polishing logic - Phase 1

For now this is a deterministic, non-LLM polish step that:
- Adds an explicit bias dimensions header to the engineered prompt
- Appends a short clarification about handling each bias dimension
- Returns a structured polished_artifact + polish_report dict

Later we can swap the internals for a real OpenAI/Groq call without
changing the function signature.
"""

from datetime import datetime
from typing import Any, Dict

from contracts.vs_bias_prompt import VSBiasPromptContract


def polish_vs_bias_prompt(contract: VSBiasPromptContract) -> Dict[str, Any]:
    """
    Perform a light-weight polish of a VS Bias prompt.

    Args:
        contract: Validated VS Bias prompt contract.

    Returns:
        Dict with:
          - polished_artifact: updated content dict
          - polish_report: metadata about what was changed
    """
    content = contract.content

    # Build a simple header from the bias dimensions
    bias_list = ", ".join(content.bias_dimensions)

    header = (
        "### BIAS DIMENSIONS TO ANALYZE\n"
        f"- Target dimensions: {bias_list}\n\n"
    )

    footer = (
        "\n\n### CLARIFICATION FOR THE MODEL\n"
        "For each generated response variant:\n"
        "- Explicitly discuss how it may reflect bias across the listed dimensions.\n"
        "- Estimate the probability that a production model would output it.\n"
        "- Highlight which dimensions are most affected and why.\n"
    )

    improved_prompt = f"{header}{content.engineered_prompt.strip()}{footer}"

    polished_artifact = {
        "user_query": content.user_query,
        "engineered_prompt": improved_prompt,
        "notes_for_lite": content.notes_for_lite,
        "bias_dimensions": content.bias_dimensions,
    }

    polish_report = {
        "summary": "Added explicit bias dimensions header and clarification block.",
        "details": [
            "Prepended a markdown header listing all bias dimensions.",
            "Appended explicit instructions for how to handle each dimension.",
            "Preserved original user query and bias dimensions.",
        ],
        "artifact_type": contract.artifact_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    return {
        "polished_artifact": polished_artifact,
        "polish_report": polish_report,
    }
