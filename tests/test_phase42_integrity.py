from pit.pit_integrity import audit_pit_rows


def test_all_known_availability_fields_are_checked_against_trade_date():
    rows = [{
        'code': '000001', 'trade_date': '2026-01-05',
        'available_at': '2026-01-04',
        'published_at': '2026-01-06',
        'asof': '2026-01-05',
    }]
    r = audit_pit_rows(rows)
    assert not r['ok']
    assert any(x.get('field') == 'published_at' for x in r['issues'])


def test_no_global_cutoff_masks_row_level_future_timestamp():
    rows = [
        {'code': '000001', 'trade_date': '2026-01-05', 'published_at': '2026-01-05'},
        {'code': '000001', 'trade_date': '2026-01-06', 'published_at': '2026-01-07'},
    ]
    r = audit_pit_rows(rows)
    assert not r['ok']
    assert any(x['index'] == 1 for x in r['issues'])
