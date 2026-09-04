"""Natural language to Strategy code, via the in-house LLM.

Validates the result with the AST checker and retries once, feeding the error back.
"""

from __future__ import annotations

from pathlib import Path

from app.lab import llm
from app.lab.config import LabConfig
from app.lab.features import FEATURE_REGISTRY
from app.lab.presets import PRESETS
from app.lab.sandbox import validate_strategy_source

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "strategy_codegen.md").read_text(encoding="utf-8")
_strip_fences = llm.strip_fences


def _build_prompt(nl_request: str, config: LabConfig, error: str | None = None) -> str:
    examples = "\n\n".join(f"## {name}\n{code}" for name, code in PRESETS.items())
    extra = sorted(FEATURE_REGISTRY.keys()) or "(none — price only)"
    prompt = _PROMPT_TEMPLATE.format(
        n_tickers=len(config.universe),
        tickers=", ".join(config.universe),
        cap=f"{config.cap:.0%}" if config.cap else "none",
        extra_features=extra,
        examples=examples,
        nl_request=nl_request,
    )
    if error:
        prompt += (f"\n\n# Previous attempt was INVALID\nError: {error}\n"
                   f"Fix it and output ONLY the corrected Python class.")
    return prompt


def _llm(prompt: str, model: str | None = None) -> str:
    """Call the LLM at temperature 0. explain.py reuses this helper."""
    return llm.chat(prompt, model=model, temperature=0.0)


def generate_strategy(nl_request: str, config: LabConfig,
                      model: str | None = None) -> str:
    """Return validated Strategy code; retries once if validation fails."""
    model = model or llm.default_model()
    code = _strip_fences(_llm(_build_prompt(nl_request, config), model))
    try:
        validate_strategy_source(code)
        return code
    except ValueError as exc:
        code2 = _strip_fences(_llm(_build_prompt(nl_request, config, str(exc)), model))
        validate_strategy_source(code2)   # raise if it still fails
        return code2
