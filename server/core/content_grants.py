"""Shared additive nonconsumable policy inside a caller-owned SQLite transaction."""
CONTENT_TYPES = ('pack', 'single', 'character', 'course_banner', 'world_song', 'world_unlock')


def expected_content(cur):
    placeholders = ','.join('?' for _ in CONTENT_TYPES)
    rows = cur.execute(
        'SELECT item_id,type FROM purchase_item WHERE type IN (' + placeholders + ') '
        'UNION SELECT item_id,type FROM item WHERE is_available=1 AND type IN (' + placeholders + ') '
        'ORDER BY type,item_id', CONTENT_TYPES + CONTENT_TYPES,
    ).fetchall()
    result = [(row[0], row[1]) for row in rows]
    if any(not isinstance(item, str) or not item or item_type not in CONTENT_TYPES for item, item_type in result):
        raise ValueError('Invalid nonconsumable content identity')
    return result


def grant_missing_content(cur, user_id):
    """Raise missing/null/zero ownership to one; never reduce or replenish a grant."""
    if not cur.connection.in_transaction:
        raise RuntimeError('Content grants require a caller-owned transaction')
    if type(user_id) is not int or user_id < 0:
        raise ValueError('Invalid content recipient identity')
    inserted, raised, unchanged = 0, 0, 0
    expected = expected_content(cur)
    for item_id, item_type in expected:
        rows = cur.execute('SELECT amount FROM user_item WHERE user_id=? AND item_id=? AND type=?',
                           (user_id, item_id, item_type)).fetchall()
        if len(rows) > 1:
            raise ValueError('Ambiguous ownership blocks additive grant')
        if not rows:
            cur.execute('INSERT INTO user_item(user_id,item_id,type,amount) VALUES(?,?,?,1)',
                        (user_id, item_id, item_type))
            inserted += 1
            continue
        amount = rows[0][0]
        if amount is not None and (type(amount) is not int or amount < 0):
            raise ValueError('Invalid existing content ownership amount')
        if amount is None or amount == 0:
            cur.execute('UPDATE user_item SET amount=1 WHERE user_id=? AND item_id=? AND type=? '
                        'AND (amount IS NULL OR amount=0)', (user_id, item_id, item_type))
            if cur.rowcount != 1:
                raise RuntimeError('Content grant changed concurrently')
            raised += 1
        else:
            unchanged += 1
    return {'expected_content': len(expected), 'inserted': inserted, 'raised_null_or_zero_to_one': raised,
            'unchanged_positive': unchanged, 'consumables_or_progress_modified': False}


def missing_content_count(cur, user_id):
    missing = 0
    for item_id, item_type in expected_content(cur):
        rows = cur.execute('SELECT amount FROM user_item WHERE user_id=? AND item_id=? AND type=?',
                           (user_id, item_id, item_type)).fetchall()
        if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] < 1:
            missing += 1
    return missing
