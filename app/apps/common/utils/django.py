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


def django_to_airdatepicker_datetime(django_format):
    format_map = {
        # Time
        "h": "hh",  # Hour (12-hour)
        "H": "H",  # Hour (24-hour)
        "i": "m",  # Minutes
        "A": "AA",  # AM/PM uppercase
        "a": "aa",  # am/pm lowercase
        "P": "h:mm AA",  # Localized time format (e.g., "2:30 PM")
        # Date
        "D": "E",  # Short weekday name
        "l": "EEEE",  # Full weekday name
        "j": "d",  # Day of month without leading zero
        "d": "dd",  # Day of month with leading zero
        "n": "M",  # Month without leading zero
        "m": "MM",  # Month with leading zero
        "M": "MMM",  # Short month name
        "F": "MMMM",  # Full month name
        "y": "yy",  # Year, 2 digits
        "Y": "yyyy",  # Year, 4 digits
    }

    result = ""
    i = 0
    while i < len(django_format):
        char = django_format[i]
        if char == "\\":  # Handle escaped characters
            if i + 1 < len(django_format):
                result += django_format[i + 1]
                i += 2
            continue

        if char in format_map:
            result += format_map[char]
        else:
            result += char
        i += 1

    return result


def django_to_airdatepicker_datetime_separated(django_format):
    format_map = {
        # Time formats
        "h": "hh",  # Hour (12-hour)
        "H": "HH",  # Hour (24-hour)
        "i": "mm",  # Minutes
        "A": "AA",  # AM/PM uppercase
        "a": "aa",  # am/pm lowercase
        "P": "h:mm aa",  # Localized time format
        # Date formats
        "D": "E",  # Short weekday name
        "l": "EEEE",  # Full weekday name
        "j": "d",  # Day of month without leading zero
        "d": "dd",  # Day of month with leading zero
        "n": "M",  # Month without leading zero
        "m": "MM",  # Month with leading zero
        "M": "MMM",  # Short month name
        "F": "MMMM",  # Full month name
        "y": "yy",  # Year, 2 digits
        "Y": "yyyy",  # Year, 4 digits
    }

    # Define which characters belong to time format
    time_chars = {"h", "H", "i", "A", "a", "P"}
    date_chars = {"D", "l", "j", "d", "n", "m", "M", "F", "y", "Y"}

    date_parts = []
    time_parts = []
    current_part = []
    is_time = False

    i = 0
    while i < len(django_format):
        char = django_format[i]

        if char == "\\":  # Handle escaped characters
            if i + 1 < len(django_format):
                current_part.append(django_format[i + 1])
                i += 2
            continue

        if char in format_map:
            if char in time_chars:
                # If we were building a date part, save it and start a time part
                if current_part and not is_time:
                    date_parts.append("".join(current_part))
                    current_part = []
                is_time = True
                current_part.append(format_map[char])
            elif char in date_chars:
                # If we were building a time part, save it and start a date part
                if current_part and is_time:
                    time_parts.append("".join(current_part))
                    current_part = []
                is_time = False
                current_part.append(format_map[char])
        else:
            # Handle separators
            if char in "/:.-":
                current_part.append(char)
            elif char == " ":
                if current_part:
                    if is_time:
                        time_parts.append("".join(current_part))
                    else:
                        date_parts.append("".join(current_part))
                    current_part = []
                current_part.append(char)

        i += 1

    # Don't forget the last part
    if current_part:
        if is_time:
            time_parts.append("".join(current_part))
        else:
            date_parts.append("".join(current_part))

    date_format = "".join(date_parts)
    time_format = "".join(time_parts)

    # Clean up multiple spaces while preserving necessary ones
    date_format = " ".join(filter(None, date_format.split()))
    time_format = " ".join(filter(None, time_format.split()))

    return date_format, time_format
