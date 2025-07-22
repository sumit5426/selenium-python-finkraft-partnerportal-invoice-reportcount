def resolve_expected_ag(pg_status: str, username: str) -> str:
    """
    Resolves the expected AG status based on the final PG status and username availability.
    """
    if pg_status == "EXCEPTION":
        return "error verifying"
    elif pg_status == "ACTIVE":
        return "valid"
    elif pg_status == "INVALID":
        return "wrong credential" if username else "not available"
    return "pending"
