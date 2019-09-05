def extract_from_header(headers, header_type):
    for header in headers:
        if header_type in header:
            for item in header:
                if item == header_type:
                    continue
                else:
                    return item.decode('ascii')
    return None
