from decimal import Decimal, ROUND_DOWN


def truncate_decimal(value, decimal_places):
    """
    Truncate a Decimal value to n decimal places without rounding.

    :param value: The Decimal value to truncate
    :param decimal_places: The number of decimal places to keep
    :return: Truncated Decimal value
    """
    multiplier = Decimal(10**decimal_places)
    return (value * multiplier).to_integral_value(rounding=ROUND_DOWN) / multiplier
