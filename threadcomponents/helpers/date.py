from datetime import datetime, timedelta

from threadcomponents.constants import DATETIME_OBJ


def to_datetime_obj(date_val, raise_error=False):
    """Function to convert a given date into a datetime object."""
    if isinstance(date_val, datetime):
        return date_val  # nothing to do if already converted

    try:
        return datetime.strptime(date_val, "%Y-%m-%d")
    except (TypeError, ValueError) as e:
        if raise_error:
            raise e

    return None


def check_input_date(date_str):
    """Function to check given a date string, it is in an acceptable format and range to be saved."""
    # Convert the given date into a datetime object to be able to do comparisons
    # Expect to raise TypeError if date_str is not a string
    given_date = to_datetime_obj(date_str, raise_error=True)

    # Establish the min and max date ranges we want dates to fall in
    date_now = datetime.now()
    max_date = datetime(date_now.year + 5, month=date_now.month, day=date_now.day, tzinfo=date_now.tzinfo)
    min_date = datetime(1970, month=1, day=1, tzinfo=date_now.tzinfo)

    # Raise a ValueError if the given date is not in this range
    if not (min_date < given_date < max_date):
        raise ValueError(f"Date `{date_str}` outside permitted range.")

    return given_date


def pre_save_date_checks(date_dict_list, mandatory_field_list, success_response):
    """Function to carry out checks when dealing with date fields. :return data-to-save, errors"""
    update_data, converted_dates, invalid_dates = dict(), dict(), []

    # If we need to check date ranges
    lower_bound_key, upper_bound_key = None, None

    for date_dict in date_dict_list:
        date_value, date_key = date_dict.get("value"), date_dict.get("field")
        is_lower, is_upper = date_dict.get("is_lower", False), date_dict.get("is_upper", False)

        lower_bound_key = date_key if is_lower else lower_bound_key
        upper_bound_key = date_key if is_upper else upper_bound_key

        try:
            # Have reasonable date values been given (not too historic/futuristic)?
            converted_dates[date_key] = check_input_date(date_value)
            # Update original dictionary for further use
            date_dict[DATETIME_OBJ] = converted_dates[date_key]

        except (TypeError, ValueError):
            if date_value:  # if not blank, store this to report back to user
                invalid_dates.append(date_value)

            elif date_key not in mandatory_field_list:  # else if blank, we will blank the value in the database
                update_data[date_key] = None
            continue

        update_data[date_key] = date_value  # else add acceptable value to dictionary to be updated with

    # Check a sensible ordering of dates have been provided if we are testing ranges
    if lower_bound_key and upper_bound_key:
        start_date_conv, end_date_conv = converted_dates.get(lower_bound_key), converted_dates.get(upper_bound_key)

        if (start_date_conv and end_date_conv) and (end_date_conv < start_date_conv):
            return None, dict(error="Incorrect ordering of dates provided.", alert_user=1)

    # Checks have passed but update success response over invalid dates
    if invalid_dates:
        msg = (
            "The following dates were ignored for being too far in the past/future, and/or being in an "
            "incorrect format: " + ", ".join(str(val) for val in invalid_dates)
        )
        success_response.update(dict(info=msg, alert_user=1))

    return update_data, None


def generate_report_expiry(data=None, **date_kwargs):
    """Function to generate an expiry date from today and add it to a data-dictionary, if provided."""
    # Prepare expiry date as str
    expiry_date = datetime.now() + timedelta(**date_kwargs)
    expiry_date_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")

    if data:
        data.update(dict(expires_on=expiry_date_str))

    return expiry_date_str
