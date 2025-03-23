import re

from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface


def check_if_public_ip(ip_address, clean=False):
    """Function to check if an IP address is public. Returns (True/False/None (invalid), IP address)."""
    if not ip_address:
        return None, None

    address_obj = None
    cleaned_ip = ip_address

    # Special case for 'localhost', make the string compatible with the IPv4Address class
    if clean and ip_address == "localhost":
        cleaned_ip = "127.0.0.1"
    to_check = [(".", IPv4Address, IPv4Interface), (None, IPv6Address, IPv6Interface)]

    # Further tidying up if this is an IP address
    for replace_delimiter, address_class, interface_class in to_check:
        if clean and replace_delimiter:
            slash_pos = cleaned_ip.rfind("/")
            prefix = cleaned_ip[:slash_pos] if slash_pos > 0 else cleaned_ip
            suffix = cleaned_ip[slash_pos:] if slash_pos > 0 else ""

            # Replace any non-word character with the delimiter; then remove any trailing/leading delimiters
            cleaned_prefix = re.sub("\\W+", replace_delimiter, prefix)
            cleaned_prefix = re.sub(re.escape(replace_delimiter) + "+$", "", cleaned_prefix)
            cleaned_prefix = re.sub("^" + re.escape(replace_delimiter) + "+", "", cleaned_prefix)
            cleaned_ip = cleaned_prefix + suffix

        # Attempt Address class before Interface class
        for obj_class in [address_class, interface_class]:
            try:
                address_obj = obj_class(cleaned_ip)
                break
            except Exception:
                continue
        if address_obj:
            break

    if not address_obj:
        # Don't return cleaned-changes as it is not applicable
        return None, ip_address
    return (not (address_obj.is_link_local or address_obj.is_multicast or address_obj.is_private)), cleaned_ip
