"""Application-level exceptions."""


class StaleUpdateError(Exception):
    """Raised when an update is attempted on a record that has been modified
    since the client last read it (optimistic concurrency conflict).

    Attributes:
        setting_key: The key/name of the setting that was stale.
        current_updated_at: The actual updated_at value in the database.
        expected_updated_at: The value the client expected.
        updated_by: Who last updated the record.
    """

    def __init__(
        self,
        setting_key: str,
        current_updated_at=None,
        expected_updated_at=None,
        updated_by: str | None = None,
    ):
        self.setting_key = setting_key
        self.current_updated_at = current_updated_at
        self.expected_updated_at = expected_updated_at
        self.updated_by = updated_by
        super().__init__(
            f"Stale update on '{setting_key}': "
            f"expected updated_at={expected_updated_at}, "
            f"but current is {current_updated_at} "
            f"(last changed by {updated_by or 'unknown'})"
        )
