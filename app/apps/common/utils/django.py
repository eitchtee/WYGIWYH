def django_to_python_datetime(django_format):
    mapping = {
        # Day
        "j": "%d",  # Day of the month without leading zeros
        "d": "%d",  # Day of the month with leading zeros
        "D": "%a",  # Day of the week, short version
        "l": "%A",  # Day of the week, full version
        # Month
        "n": "%m",  # Month without leading zeros
        "m": "%m",  # Month with leading zeros
        "M": "%b",  # Month, short version
        "F": "%B",  # Month, full version
        # Year
        "y": "%y",  # Year, 2 digits
        "Y": "%Y",  # Year, 4 digits
        # Time
        "g": "%I",  # Hour (12-hour), without leading zeros
        "G": "%H",  # Hour (24-hour), without leading zeros
        "h": "%I",  # Hour (12-hour), with leading zeros
        "H": "%H",  # Hour (24-hour), with leading zeros
        "i": "%M",  # Minutes
        "s": "%S",  # Seconds
        "a": "%p",  # am/pm
        "A": "%p",  # AM/PM
        "P": "%I:%M %p",
    }

    python_format = django_format
    for django_code, python_code in mapping.items():
        python_format = python_format.replace(django_code, python_code)

    return python_format
