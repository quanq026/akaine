class ClientPackCapacityError(ValueError):
    pass


MAX_SAFE_CLIENT_PACKS = 62


def _dedupe(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_effective_pack_list(
    db_packs,
    free_packs,
    custom_pack_ids,
    umbrella_pack_id,
    client_visible_custom_pack_ids=(),
    client_hidden_pack_ids=(),
):
    """Build effective pack entitlements without a client wire limit."""
    custom_pack_ids = set(custom_pack_ids)
    client_visible_custom_pack_ids = set(client_visible_custom_pack_ids)
    client_hidden_pack_ids = set(client_hidden_pack_ids)
    unknown_visible_ids = client_visible_custom_pack_ids - custom_pack_ids
    if unknown_visible_ids:
        raise ValueError(
            "client-visible packs must be dedicated custom packs: "
            f"{sorted(unknown_visible_ids)}"
        )
    conflicting_ids = client_visible_custom_pack_ids & client_hidden_pack_ids
    if conflicting_ids:
        raise ValueError(
            "client-visible custom packs cannot also be hidden: "
            f"{sorted(conflicting_ids)}"
        )
    hidden_custom_pack_ids = custom_pack_ids - client_visible_custom_pack_ids
    packs = _dedupe(
        pack_id
        for pack_id in [*db_packs, *free_packs]
        if pack_id not in hidden_custom_pack_ids
        and pack_id not in client_hidden_pack_ids
    )

    if (
        umbrella_pack_id not in client_hidden_pack_ids
        and (umbrella_pack_id in db_packs or umbrella_pack_id in free_packs)
    ):
        packs = _dedupe([*packs, umbrella_pack_id])

    packs = _dedupe([*packs, *sorted(client_visible_custom_pack_ids)])

    return packs


def build_client_pack_list(
    db_packs,
    free_packs,
    custom_pack_ids,
    umbrella_pack_id,
    max_client_packs,
    client_visible_custom_pack_ids=(),
    client_hidden_pack_ids=(),
    allowed_pack_ids=None,
):
    """Build the bounded entitlement list consumed by the native client."""
    if max_client_packs > MAX_SAFE_CLIENT_PACKS:
        raise ClientPackCapacityError(
            f"configured client pack limit {max_client_packs} exceeds "
            f"native safe capacity {MAX_SAFE_CLIENT_PACKS}"
        )
    packs = build_effective_pack_list(
        db_packs=db_packs,
        free_packs=free_packs,
        custom_pack_ids=custom_pack_ids,
        umbrella_pack_id=umbrella_pack_id,
        client_visible_custom_pack_ids=client_visible_custom_pack_ids,
        client_hidden_pack_ids=client_hidden_pack_ids,
    )
    if allowed_pack_ids is not None:
        available_packs = set(packs)
        packs = [
            pack_id
            for pack_id in _dedupe(allowed_pack_ids)
            if pack_id in available_packs
        ]

    if len(packs) > max_client_packs:
        raise ClientPackCapacityError(
            f"client pack payload has {len(packs)} entries; "
            f"operational limit is {max_client_packs}"
        )

    return packs


def expand_pack_unlocks(
    client_pack_ids,
    pack_songs,
    umbrella_pack_id,
    custom_pack_ids,
):
    """Expand the shared fan entitlement only for server-side authorization."""
    effective_pack_ids = set(client_pack_ids)
    if umbrella_pack_id in effective_pack_ids:
        effective_pack_ids.update(custom_pack_ids)

    result = set()
    for pack_id in effective_pack_ids:
        result.update(pack_songs.get(pack_id, ()))
    return result
