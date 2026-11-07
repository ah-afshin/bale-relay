def chunks(text, limit=3500):
    # Reserve room for numbering and avoid splitting surrogate pairs on UTF-16 clients.
    parts, current, size = [], [], 0
    for char in text:
        width = len(char.encode("utf-16-le")) // 2
        if size + width > limit - 32:
            parts.append("".join(current)); current, size = [], 0
        current.append(char); size += width
    if current: parts.append("".join(current))
    if len(parts) < 2: return parts
    return [f"({i}/{len(parts)})\n{part}" for i, part in enumerate(parts, 1)]
