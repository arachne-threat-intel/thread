# Copied from here: https://stackoverflow.com/a/480227
def dedup_list(list):
    seen = set()
    seen_add = seen.add
    return [x for x in list if not (x in seen or seen_add(x))]
