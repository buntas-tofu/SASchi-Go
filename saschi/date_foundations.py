"""FMT-01 canonical date reference foundations; source admission stays separate."""
import datetime
import re

from sas_semantics import (SAS_EPOCH, SAS_CALENDAR_MIN_DAY, SAS_CALENDAR_MAX_DAY,
                           sas_calendar, sas_calendar_integer)

# FMT-01 reference foundations; source-level admission is a separate contract.
SAS_DATE_MONTH_NAMES = ('January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December')
SAS_DATE_WEEKDAY_NAMES = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


def sas_input_date9(token):
    """Canonical DDMMMYYYY or ordinary missing, within the calendar profile."""
    if type(token) is not str:
        raise ValueError('DATE9 requires canonical ASCII text or a period')
    if token == '.':
        return None
    match = re.fullmatch(r'([0-9]{2})([A-Za-z]{3})([0-9]{4})', token, re.ASCII)
    if match is None:
        raise ValueError('DATE9 requires exactly DDMMMYYYY; other forms require review')
    months = tuple(name[:3].upper() for name in SAS_DATE_MONTH_NAMES)
    try:
        month = months.index(match[2].upper()) + 1
    except ValueError as error:
        raise ValueError('DATE9 requires an English month abbreviation') from error
    return sas_calendar('mdy', month, int(match[1]), int(match[3]))


def sas_date_field(value, format_name, width):
    """Complete English WEEKDATE/WORDDATE fields, with explicit wide bounds."""
    if (type(format_name) is not str or not format_name.isascii()
            or format_name.lower() not in ('weekdate', 'worddate') or type(width) is not int):
        raise ValueError('date field requires a named full-date format and integer width')
    name = format_name.lower()
    lower, upper = (29, 37) if name == 'weekdate' else (18, 32)
    if not lower <= width <= upper:
        raise ValueError('date field width is outside the qualified complete-name subset')
    if value is None:
        return '.'.rjust(width)
    day = sas_calendar_integer(value, SAS_CALENDAR_MIN_DAY, SAS_CALENDAR_MAX_DAY)
    date = SAS_EPOCH + datetime.timedelta(days=day)
    text = f'{SAS_DATE_MONTH_NAMES[date.month-1]} {date.day}, {date.year:04d}'
    if name == 'weekdate':
        text = SAS_DATE_WEEKDAY_NAMES[date.weekday()] + ', ' + text
    return text.rjust(width)
