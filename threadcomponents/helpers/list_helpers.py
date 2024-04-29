# Copied from here: https://stackoverflow.com/a/480227
def dedup_list(list_to_dedupe):
    seen = set()
    seen_add = seen.add
    return [x for x in list_to_dedupe if not (x in seen or seen_add(x))]
