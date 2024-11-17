def remove_falsey_entries(data: dict, key: str) -> dict:
    return {k: v for k, v in data.items() if v.get(key)}
