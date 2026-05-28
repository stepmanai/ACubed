# storage/naming.py


def build_table_name(
    layer: str,
    table: str,
):
    return f"{layer}.{table}"
