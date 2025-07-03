class RetryableOpenAIError(Exception):
    """Exception raised when an OpenAI call failed for a reason that should be retried later."""
    pass 