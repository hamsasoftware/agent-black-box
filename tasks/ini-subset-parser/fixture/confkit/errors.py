class ParseError(ValueError):
    """A syntax or consistency error in a document; see docs/FORMAT.md."""

    def __init__(self, message, lineno, source="<string>"):
        super().__init__(f"{source}:{lineno}: {message}")
        self.message = message
        self.lineno = lineno
        self.source = source
