# Firms confirmed to be non-PI entities (vendors, tech companies, etc).
# Research, website resolution, behavior analysis, and PIF status extraction
# must not be triggered for these firm IDs.
NON_PI_FIRM_IDS: frozenset[str] = frozenset({
    "aba1a98b-abe4-4796-bbd6-8e3a8aef5820",  # Accilink
    "ae167dfd-152d-4efa-897d-f8255d51f036",  # Newflex Group
    "0e9b8345-c5b7-4f1e-8b0f-042f303ea7f3",  # WestFax
})
