from app.importers import load_members, normalize_username


def test_normalizes_at_username():
    assert normalize_username("@Timal_123") == "timal_123"


def test_normalizes_tme_url():
    assert normalize_username("https://t.me/Timal_123") == "timal_123"


def test_rejects_invalid_username():
    assert normalize_username("@@bad name") is None


def test_loads_combined_id_username_mapping(tmp_path):
    path = tmp_path / "mapping.csv"
    path.write_text(
        "telegram_id,username,all_usernames_seen\n"
        "653422727,@guevarauhq,@guevarauhq\n"
        "670487602,,@Abacule | @AbaculeOld\n"
        "123456789,,\n",
        encoding="utf-8",
    )
    rows = load_members(path)
    assert [(x.telegram_user_id, x.username) for x in rows] == [
        (653422727, "guevarauhq"),
        (670487602, "abacule"),
        (670487602, "abaculeold"),
        (123456789, None),
    ]
