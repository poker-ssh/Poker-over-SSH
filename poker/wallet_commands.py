"""
Wallet command handlers for Poker-over-SSH
Contains all wallet-related command implementations.
"""

import logging
from poker.terminal_ui import Colors


async def handle_wallet(session):
    """Handle wallet command - show wallet info."""
    try:
        if not session._username:
            session._stdout.write("❌ Username required for wallet operations\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        from poker.wallet import get_wallet_manager
        wallet_manager = get_wallet_manager()
        
        wallet_info = wallet_manager.format_wallet_info(session._username)
        session._stdout.write(f"{wallet_info}\r\n\r\n❯ ")
        await session._stdout.drain()
    except Exception as e:
        session._stdout.write(f"❌ Error showing wallet: {e}\r\n\r\n❯ ")
        await session._stdout.drain()


async def handle_wallet_command(session, cmd: str):
    """Handle wallet subcommands."""
    try:
        if not session._username:
            session._stdout.write("❌ Username required for wallet operations\r\n\r\n❯ ")
            await session._stdout.drain()
            return
        
        parts = cmd.split()
        if len(parts) < 2:
            await handle_wallet(session)
            return
        
        subcmd = parts[1].lower()
        
        from poker.wallet import get_wallet_manager
        wallet_manager = get_wallet_manager()
        
        if subcmd == "history":
            history = wallet_manager.format_transaction_history(session._username, 15)
            session._stdout.write(f"{history}\r\n\r\n❯ ")
            
        elif subcmd == "actions":
            actions = wallet_manager.get_action_history(session._username, 20)
            session._stdout.write(f"{Colors.BOLD}{Colors.CYAN}🎮 Recent Game Actions{Colors.RESET}\r\n")
            session._stdout.write("=" * 50 + "\r\n")
            
            if not actions:
                session._stdout.write(f"{Colors.DIM}No game actions found.{Colors.RESET}\r\n")
            else:
                for action in actions:
                    import time
                    timestamp = time.strftime("%m-%d %H:%M", time.localtime(action['timestamp']))
                    action_type = action['action_type'].replace('_', ' ').title()
                    amount = action['amount']
                    room = action['room_code']
                    
                    line = f"  {timestamp} | {action_type:<15} | ${amount:<6} | Room: {room}"
                    if action['details']:
                        line += f"\r\n    {Colors.DIM}{action['details']}{Colors.RESET}"
                    
                    session._stdout.write(line + "\r\n")
            
            session._stdout.write("\r\n❯ ")
            
        elif subcmd == "leaderboard":
            leaderboard = wallet_manager.get_leaderboard()
            session._stdout.write(f"{leaderboard}\r\n\r\n❯ ")
            
        elif subcmd == "add":
            # Claim hourly bonus
            success, message = wallet_manager.claim_hourly_bonus(session._username)
            session._stdout.write(f"{message}\r\n\r\n❯ ")
            
        elif subcmd == "save":
            # Manual save to database
            success = wallet_manager.save_wallet_to_database(session._username)
            if success:
                session._stdout.write(f"✅ Wallet saved to database successfully!\r\n\r\n❯ ")
            else:
                session._stdout.write(f"❌ Failed to save wallet to database\r\n\r\n❯ ")
                
        elif subcmd == "saveall":
            # Admin command to save all cached wallets
            if session._username in ['root']:  # Basic admin check
                saved_count = wallet_manager.save_all_wallets()
                session._stdout.write(f"✅ Saved {saved_count} wallets to database\r\n\r\n❯ ")
            else:
                session._stdout.write(f"❌ Admin privileges required for saveall command\r\n\r\n❯ ")
                
        elif subcmd == "check":
            # Admin command to check database integrity
            if session._username in ['root']:  # Basic admin check
                from poker.database import get_database
                db = get_database()
                issues = db.check_database_integrity()
                
                if not issues:
                    session._stdout.write(f"✅ Database integrity check passed - no issues found\r\n\r\n❯ ")
                else:
                    session._stdout.write(f"⚠️  Database integrity check found {len(issues)} issue(s):\r\n")
                    for issue in issues[:10]:  # Limit to first 10 issues
                        session._stdout.write(f"  • {issue}\r\n")
                    if len(issues) > 10:
                        session._stdout.write(f"  ... and {len(issues) - 10} more issues\r\n")
                    session._stdout.write("\r\n❯ ")
            else:
                session._stdout.write(f"❌ Admin privileges required for check command\r\n\r\n❯ ")
                
        elif subcmd == "audit":
            # Admin command to audit specific player's transactions
            if session._username in ['root']:  # Basic admin check
                if len(parts) < 3:
                    session._stdout.write(f"❌ Usage: wallet audit <player_name>\r\n\r\n❯ ")
                else:
                    target_player = parts[2]
                    from poker.database import get_database
                    db = get_database()
                    audit_result = db.audit_player_transactions(target_player)
                    
                    if "error" in audit_result:
                        session._stdout.write(f"❌ {audit_result['error']}\r\n\r\n❯ ")
                    else:
                        session._stdout.write(f"🔍 Transaction Audit for {audit_result['player_name']}:\r\n")
                        session._stdout.write(f"  Current Balance: ${audit_result['current_balance']}\r\n")
                        session._stdout.write(f"  Transaction Count: {audit_result['transaction_count']}\r\n")
                        session._stdout.write(f"  Total Credits: ${audit_result['summary']['total_credits']}\r\n")
                        session._stdout.write(f"  Total Debits: ${audit_result['summary']['total_debits']}\r\n")
                        session._stdout.write(f"  Net Change: ${audit_result['summary']['net_change']:+}\r\n")
                        session._stdout.write(f"  Calculated Balance: ${audit_result['summary']['calculated_balance']}\r\n")
                        
                        if audit_result['issues']:
                            session._stdout.write(f"\r\n⚠️  Found {len(audit_result['issues'])} issue(s):\r\n")
                            for issue in audit_result['issues'][:5]:  # Limit output
                                session._stdout.write(f"  • {issue}\r\n")
                            if len(audit_result['issues']) > 5:
                                session._stdout.write(f"  ... and {len(audit_result['issues']) - 5} more issues\r\n")
                        else:
                            session._stdout.write(f"\r\n✅ No issues found in transaction history\r\n")
                        session._stdout.write("\r\n❯ ")
            else:
                session._stdout.write(f"❌ Admin privileges required for audit command\r\n\r\n❯ ")
                    
        else:
            session._stdout.write(f"❌ Unknown wallet command: {subcmd}\r\n")
            session._stdout.write("💡 Available: history, actions, leaderboard, add, save, saveall, check, audit\r\n\r\n❯ ")
        
        await session._stdout.drain()
        
    except Exception as e:
        session._stdout.write(f"❌ Error in wallet command: {e}\r\n\r\n❯ ")
        await session._stdout.drain()