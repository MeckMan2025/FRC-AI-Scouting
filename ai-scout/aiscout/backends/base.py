class UsageLimit(Exception):
    """The model hit a usage/rate limit; retry after `resume_at` (epoch seconds) if known."""
    def __init__(self, msg, resume_at=None):
        super().__init__(msg)
        self.resume_at = resume_at


class Backend:
    """Looks at image files and answers with JSON matching a schema."""
    name = "base"

    def ask(self, prompt, images, schema, workdir):
        """Return (data: dict, usage: dict). Raise UsageLimit when out of quota."""
        raise NotImplementedError
