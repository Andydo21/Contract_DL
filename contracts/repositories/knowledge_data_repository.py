"""Version-bound case queries and locked revision updates."""


def get_record(records, **filters):
    if hasattr(records, '_default_manager'):
        records = records._default_manager
    return records.get(**filters)
