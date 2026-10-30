def make(cfg):
    """The backend chosen in config.json: "claude-code" (default, uses the Max plan) or "ollama" (local)."""
    if cfg.get("backend") == "ollama":
        from .ollama import Ollama
        return Ollama(model=cfg.get("ollama_model"))
    from .claude_code import ClaudeCode
    return ClaudeCode(model=cfg.get("model"))
