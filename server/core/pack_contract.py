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


def validated_catalog_pack_ids(pack_rows):
    """Run once for a pinned release catalog, never on the request hot path."""
    pack_ids = []
    parents = {}
    for row in pack_rows:
        if not isinstance(row, dict):
            raise ValueError('invalid catalog pack row')
        pack_id = row.get('id')
        if not isinstance(pack_id, str) or not pack_id or pack_id in parents:
            raise ValueError('invalid or duplicate catalog pack ID')
        parent = row.get('pack_parent')
        if parent is not None and (not isinstance(parent, str) or not parent):
            raise ValueError('invalid catalog pack parent')
        pack_ids.append(pack_id)
        parents[pack_id] = parent
    if not pack_ids:
        raise ValueError('empty catalog pack list')
    completed = set()
    for pack_id in pack_ids:
        pending = set()
        current = pack_id
        while current is not None and current not in completed:
            if current not in parents:
                raise ValueError('catalog pack parent is absent')
            if current in pending:
                raise ValueError('catalog pack parent cycle')
            pending.add(current)
            current = parents[current]
        completed.update(pending)
    return tuple(pack_ids)


def dynamic_pack_profile_enabled(app_version, feature_header, enabled=False):
    """Representation selection only; this never authorizes a pack grant."""
    return enabled is True and app_version == '7.0.255' and feature_header == 'dynamic1'


def project_owned_catalog_packs(
    catalog_pack_ids,
    db_owned_pack_ids,
    free_pack_ids=(),
    hidden_pack_ids=(),
    visible_pack_ids=None,
    entitlement_expansions=None,
    *,
    profile_enabled=False,
    capacity_accepted=False,
):
    """New-client candidate only; no caller may enable it before native proof."""
    if profile_enabled is not True or capacity_accepted is not True:
        raise ClientPackCapacityError('dynamic pack client profile is not approved')
    catalog = tuple(catalog_pack_ids)
    known = set(catalog)
    if not catalog or len(known) != len(catalog) or any(not isinstance(x, str) or not x for x in catalog):
        raise ValueError('invalid validated catalog IDs')
    expansions = entitlement_expansions or {}
    if not isinstance(expansions, dict):
        raise ValueError('invalid entitlement expansion policy')
    expansions = dict(expansions)
    for alias, targets in expansions.items():
        if not isinstance(alias, str) or not alias or isinstance(targets, str):
            raise ValueError('invalid entitlement expansion')
        expansions[alias] = tuple(targets)
        if not set(expansions[alias]) <= known:
            raise ValueError('unknown expanded catalog pack')
    free = set(free_pack_ids)
    hidden = set(hidden_pack_ids)
    visible = known if visible_pack_ids is None else set(visible_pack_ids)
    if not free <= known | expansions.keys() or not hidden <= known or not visible <= known:
        raise ValueError('unknown catalog pack in release policy')
    authorized = set(db_owned_pack_ids) | free
    # Visibility and pack_parent never grant ownership. Aliases are explicit policy.
    granted_aliases = frozenset(authorized)
    for alias, targets in expansions.items():
        if alias in granted_aliases:
            authorized.update(targets)
    result = [pack_id for pack_id in catalog if pack_id in authorized and pack_id in visible and pack_id not in hidden]
    return result
