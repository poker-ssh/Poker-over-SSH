#!/usr/bin/env python3
"""
Database diagnostic tool for Poker-over-SSH.
Run this script to check for common database integrity issues.
"""

import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poker.database import get_database


def main():
    """Run database diagnostics."""
    print("🔍 Poker-over-SSH Database Diagnostic Tool")
    print("=" * 50)
    
    try:
        db = get_database()
        
        # Get basic stats
        print("\n📊 Database Statistics:")
        stats = db.get_database_stats()
        print(f"  Total Wallets: {stats['total_wallets']}")
        print(f"  Total Transactions: {stats['total_transactions']}")
        print(f"  Total Actions: {stats['total_actions']}")
        print(f"  Active Players (7 days): {stats['active_players']}")
        print(f"  Total Money in Circulation: ${stats['total_balance']:,}")
        print(f"  Suspicious Large Balances: {stats.get('suspicious_balances', 'N/A')}")
        
        # Check for integrity issues
        print("\n🔍 Integrity Check:")
        issues = db.check_database_integrity()
        
        if not issues:
            print("  ✅ No integrity issues found!")
        else:
            print(f"  ⚠️  Found {len(issues)} issue(s):")
            for i, issue in enumerate(issues, 1):
                print(f"    {i}. {issue}")
        
        # Show top players by balance
        print("\n🏆 Top 5 Players by Balance:")
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT player_name, balance, total_winnings, total_losses, games_played
                FROM wallets 
                ORDER BY balance DESC 
                LIMIT 5
            """)
            top_players = cursor.fetchall()
            
            for i, player in enumerate(top_players, 1):
                net = player['total_winnings'] - player['total_losses']
                print(f"    {i}. {player['player_name']:<15} - Balance: ${player['balance']:>8,} | "
                      f"Net: ${net:>8,} | Games: {player['games_played']:>3}")
        
        # Check for recent large transactions
        print("\n💸 Recent Large Transactions (>$1000):")
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT player_name, transaction_type, amount, balance_after, 
                       datetime(timestamp, 'unixepoch', 'localtime') as time_local,
                       description
                FROM transactions 
                WHERE ABS(amount) > 1000 
                ORDER BY timestamp DESC 
                LIMIT 10
            """)
            large_txns = cursor.fetchall()
            
            if not large_txns:
                print("    No large transactions found")
            else:
                for txn in large_txns:
                    print(f"    {txn['player_name']:<15} | {txn['transaction_type']:<12} | "
                          f"${txn['amount']:>8,} | New Balance: ${txn['balance_after']:>8,} | "
                          f"{txn['time_local']}")
        
        print(f"\n✅ Database diagnostic complete!")
        
    except Exception as e:
        print(f"❌ Error running diagnostics: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
