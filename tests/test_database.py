from poker.database import DatabaseManager, get_database, init_database


def test_database_wallet_and_transactions(database_manager):
    db = database_manager

    wallet = db.get_wallet("alice")
    assert wallet["balance"] == 500

    db.add_wallet_funds("alice", 200, "signup bonus")
    updated_wallet = db.get_wallet("alice")
    assert updated_wallet["balance"] == 700

    db.update_wallet_balance("alice", 900, "GAME_RESULT", "Round result")
    db.log_action("alice", "room1", "BET", 50, round_id="round1", game_phase="flop", details="raise")
    db.log_transaction("alice", "CUSTOM", 25, 900, 925, "custom adj")

    actions = db.get_player_actions("alice")
    transactions = db.get_player_transactions("alice")
    assert actions and transactions

    db.update_game_stats("alice", winnings_change=80)
    leaderboard = db.get_leaderboard()
    assert any(entry["player_name"] == "alice" for entry in leaderboard)

    removed = db.cleanup_old_data(0)
    assert removed >= 1

    stats = db.get_database_stats()
    assert set(["total_wallets", "total_actions", "total_transactions", "active_players", "total_balance", "suspicious_balances"]) <= set(stats.keys())

    audit = db.audit_player_transactions("alice")
    assert audit["player_name"] == "alice"
    assert "transaction_count" in audit

    integrity = db.check_database_integrity()
    assert isinstance(integrity, list)



def test_database_admin_features(database_manager):
    db = database_manager

    assert db.register_ssh_key("alice", "ssh-rsa AAA", "rsa", "laptop") is True
    assert db.register_ssh_key("alice", "ssh-rsa AAA", "rsa", "laptop") is False
    assert db.register_ssh_key("bob", "ssh-ed25519 BBB", "ed25519", "tablet") is True

    keys = db.get_authorized_keys("alice")
    assert len(keys) == 1
    assert db.is_key_authorized("alice", "ssh-rsa AAA") is True
    assert db.is_key_authorized("alice", "ssh-rsa MISSING") is False

    db.update_key_last_used("alice", "ssh-rsa AAA")
    all_keys = db.get_all_ssh_keys()
    assert len(all_keys) == 2
    assert set(db.get_users_with_keys()) == {"alice", "bob"}
    assert db.get_key_owner("ssh-rsa AAA") == "alice"
    assert db.is_key_registered_elsewhere("bob", "ssh-rsa AAA") is True
    assert db.remove_ssh_key("bob", "ssh-ed25519 BBB") is True

    can_claim, _ = db.can_claim_bonus("alice")
    assert can_claim is True
    assert db.claim_bonus("alice", amount=150) is True
    can_claim, _ = db.can_claim_bonus("alice")
    assert can_claim is False

    db.mark_ai_broke("bot")
    assert db.can_ai_respawn("bot") is False
    with db.get_cursor() as cursor:
        cursor.execute("UPDATE ai_respawns SET respawn_time = ? WHERE ai_name = ?", (0, "bot"))
    assert db.can_ai_respawn("bot") is True
    db.respawn_ai("bot")

    assert db.is_guest_account("guest")
    db.update_guest_activity("guest")
    db.touch_guest_activity("guest")
    usernames = db.list_guest_usernames()
    assert "guest" in usernames

    with db.get_cursor() as cursor:
        cursor.execute("UPDATE guest_accounts SET last_activity = ? WHERE username = ?", (0, "guest"))
    assert db.should_reset_guest_account("guest", inactivity_hours=0) is True
    assert db.reset_guest_account("guest") is True
    reset_info = db.get_guest_reset_info("guest")
    assert reset_info["total_resets"] >= 1

    allocated = db.allocate_guest_username(max_guest=2)
    assert allocated in {"guest1", "guest2"}

    db.touch_guest_activity(allocated)


def test_database_singleton_helpers(tmp_path, monkeypatch):
    path = tmp_path / "standalone.sqlite"
    manager = init_database(str(path))
    try:
        assert isinstance(get_database(), DatabaseManager)
        wallet = manager.get_wallet("singleton")
        assert wallet["player_name"] == "singleton"
    finally:
        try:
            manager._get_connection().close()
        except Exception:
            pass
        monkeypatch.setattr("poker.database._db_manager", None, raising=False)
