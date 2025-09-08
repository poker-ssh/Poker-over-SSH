"""
Health monitoring and audit database operations for Poker-over-SSH.
Handles database integrity checks, audits, and health monitoring.
"""

import time
import json
import logging
from typing import List, Dict, Any


class HealthAuditDatabaseMixin:
    """Mixin class providing health monitoring and audit database operations."""
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_cursor() as cursor:
            # Get wallet counts
            cursor.execute("SELECT COUNT(*) as count FROM wallets")
            wallet_count = cursor.fetchone()['count']
            
            # Get transaction counts
            cursor.execute("SELECT COUNT(*) as count FROM transactions")
            transaction_count = cursor.fetchone()['count']
            
            # Get action counts
            cursor.execute("SELECT COUNT(*) as count FROM actions")
            action_count = cursor.fetchone()['count']
            
            # Get total balance
            cursor.execute("SELECT SUM(balance) as total FROM wallets")
            total_balance = cursor.fetchone()['total'] or 0
            
            return {
                'total_wallets': wallet_count,
                'total_transactions': transaction_count,
                'total_actions': action_count,
                'total_balance_in_circulation': total_balance
            }
    
    def check_database_integrity(self) -> List[str]:
        """Check database for potential integrity issues."""
        issues = []
        
        with self.get_cursor() as cursor:
            # Check for wallets with excessive balances
            cursor.execute("SELECT player_name, balance FROM wallets WHERE balance > 100000")
            large_balances = cursor.fetchall()
            for row in large_balances:
                issues.append(f"Suspicious large balance: {row['player_name']} has ${row['balance']}")
            
            # Check for negative balances
            cursor.execute("SELECT player_name, balance FROM wallets WHERE balance < 0")
            negative_balances = cursor.fetchall()
            for row in negative_balances:
                issues.append(f"Negative balance: {row['player_name']} has ${row['balance']}")
            
            # Check for transaction inconsistencies
            cursor.execute("""
                SELECT player_name, COUNT(*) as count, 
                       SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as credits,
                       SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as debits
                FROM transactions 
                WHERE transaction_type != 'WALLET_CREATED'
                GROUP BY player_name
                HAVING COUNT(*) > 100
            """)
            heavy_activity = cursor.fetchall()
            for row in heavy_activity:
                issues.append(f"Heavy transaction activity: {row['player_name']} has {row['count']} transactions")
            
            # Check for players with huge win/loss streaks
            cursor.execute("""
                SELECT player_name, total_winnings, total_losses, balance,
                       (total_winnings - total_losses) as net
                FROM wallets 
                WHERE total_winnings > 50000 OR total_losses > 50000 OR ABS(total_winnings - total_losses) > 75000
            """)
            extreme_stats = cursor.fetchall()
            for row in extreme_stats:
                issues.append(f"Extreme stats: {row['player_name']} - Winnings: ${row['total_winnings']}, Losses: ${row['total_losses']}, Net: ${row['net']}")
        
        return issues

    def audit_player_transactions(self, player_name: str) -> Dict[str, Any]:
        """Audit a player's transactions for inconsistencies."""
        with self.get_cursor() as cursor:
            # Get wallet info
            cursor.execute("SELECT * FROM wallets WHERE player_name = ?", (player_name,))
            wallet = cursor.fetchone()
            if not wallet:
                return {"error": "Player not found"}
            
            # Get all transactions
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE player_name = ? 
                ORDER BY timestamp ASC
            """, (player_name,))
            transactions = cursor.fetchall()
            
            audit_result = {
                "player_name": player_name,
                "current_balance": wallet['balance'],
                "transaction_count": len(transactions),
                "issues": [],
                "summary": {
                    "total_credits": 0,
                    "total_debits": 0,
                    "net_change": 0,
                    "calculated_balance": 500  # Starting balance
                }
            }
            
            expected_balance = 500  # Starting balance for new wallets
            
            for i, tx in enumerate(transactions):
                # Check if balance_after matches calculated balance
                if tx['transaction_type'] == 'WALLET_CREATED':
                    expected_balance = tx['balance_after']
                else:
                    expected_balance += tx['amount']
                
                if tx['balance_after'] != expected_balance:
                    audit_result["issues"].append(f"Transaction {i+1}: Expected balance ${expected_balance}, got ${tx['balance_after']}")
                
                # Check if amount matches balance difference
                actual_change = tx['balance_after'] - tx['balance_before']
                if actual_change != tx['amount']:
                    audit_result["issues"].append(f"Transaction {i+1}: Amount ${tx['amount']} doesn't match balance change ${actual_change}")
                
                # Accumulate totals
                if tx['amount'] > 0:
                    audit_result["summary"]["total_credits"] += tx['amount']
                else:
                    audit_result["summary"]["total_debits"] += abs(tx['amount'])
            
            audit_result["summary"]["net_change"] = audit_result["summary"]["total_credits"] - audit_result["summary"]["total_debits"]
            audit_result["summary"]["calculated_balance"] = expected_balance
            
            # Check if calculated balance matches current wallet balance
            if expected_balance != wallet['balance']:
                audit_result["issues"].append(f"Final balance mismatch: Calculated ${expected_balance}, Wallet shows ${wallet['balance']}")
            
            return audit_result

    def log_health_entry(self, ts: int, status: str, probe: Dict[str, Any]) -> int:
        """Insert a healthcheck history entry. Probe dict stored as JSON."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO health_history (ts, status, probe, created_at) VALUES (?, ?, ?, ?)",
                (ts, status, json.dumps(probe), time.time())
            )
            return cursor.lastrowid or 0

    def get_health_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent health history entries, most recent first."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT ts, status, probe, created_at FROM health_history ORDER BY ts DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                try:
                    probe = json.loads(row['probe']) if row['probe'] else None
                except json.JSONDecodeError:
                    probe = {"error": "Could not decode probe data"}
                
                result.append({
                    "ts": row['ts'],
                    "status": row['status'],
                    "probe": probe,
                    "created_at": row['created_at']
                })
            return result