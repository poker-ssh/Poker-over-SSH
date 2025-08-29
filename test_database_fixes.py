#!/usr/bin/env python3
"""
Test script to verify database fixes and check for any remaining issues.
"""

import sys
import os
import time

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poker.database import get_database, init_database
from poker.wallet import get_wallet_manager


def test_wallet_creation_consistency():
    """Test that wallet creation is consistent between code and schema."""
    print("🧪 Testing wallet creation consistency...")
    
    db = get_database()
    wallet_manager = get_wallet_manager()
    
    test_user = f"schema_test_{int(time.time())}"
    
    # Test 1: Direct database wallet creation
    db_wallet = db.get_wallet(test_user)
    print(f"  Direct DB wallet creation: ${db_wallet['balance']}")
    
    # Test 2: Wallet manager creation
    test_user2 = f"manager_test_{int(time.time())}"
    manager_wallet = wallet_manager.get_player_wallet(test_user2)
    print(f"  Wallet manager creation: ${manager_wallet['balance']}")
    
    # Test 3: Check that both methods create wallets with same balance
    if db_wallet['balance'] == manager_wallet['balance'] == 500:
        print("  ✅ Wallet creation is consistent ($500)")
        return True
    else:
        print(f"  ❌ Inconsistency detected! DB: ${db_wallet['balance']}, Manager: ${manager_wallet['balance']}")
        return False


def test_balance_update_consistency():
    """Test that balance updates work correctly."""
    print("\n🧪 Testing balance update consistency...")
    
    db = get_database()
    test_user = f"balance_test_{int(time.time())}"
    
    # Create wallet
    wallet = db.get_wallet(test_user)
    initial_balance = wallet['balance']
    print(f"  Initial balance: ${initial_balance}")
    
    # Update balance
    new_balance = 750
    success = db.update_wallet_balance(test_user, new_balance, 'TEST_UPDATE', 'Testing balance update')
    
    # Verify update
    updated_wallet = db.get_wallet(test_user)
    print(f"  Updated balance: ${updated_wallet['balance']}")
    
    # Check transaction log
    transactions = db.get_player_transactions(test_user, 10)
    update_tx = next((tx for tx in transactions if tx['transaction_type'] == 'TEST_UPDATE'), None)
    
    if update_tx:
        expected_change = new_balance - initial_balance
        actual_change = update_tx['amount']
        print(f"  Transaction amount: ${actual_change} (expected: ${expected_change})")
        
        if actual_change == expected_change and updated_wallet['balance'] == new_balance:
            print("  ✅ Balance update is consistent")
            return True
        else:
            print("  ❌ Balance update inconsistency detected!")
            return False
    else:
        print("  ❌ Transaction not logged!")
        return False


def test_audit_functionality():
    """Test the audit functionality."""
    print("\n🧪 Testing audit functionality...")
    
    db = get_database()
    test_user = f"audit_test_{int(time.time())}"
    
    # Create wallet and do some transactions
    wallet = db.get_wallet(test_user)
    db.update_wallet_balance(test_user, 600, 'GAME_WIN', 'Test win')
    db.update_wallet_balance(test_user, 450, 'GAME_LOSS', 'Test loss')
    
    # Run audit
    audit_result = db.audit_player_transactions(test_user)
    
    if "error" in audit_result:
        print(f"  ❌ Audit error: {audit_result['error']}")
        return False
    
    print(f"  Player: {audit_result['player_name']}")
    print(f"  Current balance: ${audit_result['current_balance']}")
    print(f"  Transaction count: {audit_result['transaction_count']}")
    print(f"  Issues found: {len(audit_result['issues'])}")
    
    if audit_result['issues']:
        print("  Issues:")
        for issue in audit_result['issues'][:3]:
            print(f"    - {issue}")
    
    if len(audit_result['issues']) == 0:
        print("  ✅ Audit passed - no issues found")
        return True
    else:
        print(f"  ⚠️  Audit found {len(audit_result['issues'])} issues")
        return False


def test_edge_cases():
    """Test edge cases that could cause issues."""
    print("\n🧪 Testing edge cases...")
    
    db = get_database()
    issues_found = 0
    
    # Test 1: Zero balance handling
    test_user1 = f"zero_test_{int(time.time())}"
    wallet = db.get_wallet(test_user1)
    db.update_wallet_balance(test_user1, 0, 'BROKE', 'Player went broke')
    zero_wallet = db.get_wallet(test_user1)
    if zero_wallet['balance'] == 0:
        print("  ✅ Zero balance handled correctly")
    else:
        print(f"  ❌ Zero balance issue: expected 0, got {zero_wallet['balance']}")
        issues_found += 1
    
    # Test 2: Large balance handling
    test_user2 = f"large_test_{int(time.time())}"
    wallet = db.get_wallet(test_user2)
    try:
        db.update_wallet_balance(test_user2, 999999, 'LARGE_WIN', 'Testing large balance')
        large_wallet = db.get_wallet(test_user2)
        print(f"  ✅ Large balance handled: ${large_wallet['balance']}")
    except Exception as e:
        print(f"  ❌ Large balance error: {e}")
        issues_found += 1
    
    # Test 3: Negative balance attempt
    test_user3 = f"negative_test_{int(time.time())}"
    wallet = db.get_wallet(test_user3)
    try:
        db.update_wallet_balance(test_user3, -100, 'NEGATIVE_TEST', 'Testing negative balance')
        negative_wallet = db.get_wallet(test_user3)
        print(f"  ⚠️  Negative balance allowed: ${negative_wallet['balance']}")
        # This might be intentional for debt tracking, so not counting as error
    except Exception as e:
        print(f"  ✅ Negative balance prevented: {e}")
    
    return issues_found == 0


def main():
    """Run comprehensive database tests."""
    print("🔧 Database Integrity & Fix Verification Tests")
    print("=" * 55)
    
    try:
        # Run tests
        test1_passed = test_wallet_creation_consistency()
        test2_passed = test_balance_update_consistency()
        test3_passed = test_audit_functionality()
        test4_passed = test_edge_cases()
        
        # Summary
        print(f"\n📋 Test Summary:")
        print(f"  Wallet creation consistency: {'✅ PASS' if test1_passed else '❌ FAIL'}")
        print(f"  Balance update consistency: {'✅ PASS' if test2_passed else '❌ FAIL'}")
        print(f"  Audit functionality: {'✅ PASS' if test3_passed else '❌ FAIL'}")
        print(f"  Edge case handling: {'✅ PASS' if test4_passed else '❌ FAIL'}")
        
        if all([test1_passed, test2_passed, test3_passed, test4_passed]):
            print(f"\n🎉 All database tests passed! No errors found.")
            return 0
        else:
            print(f"\n⚠️  Some tests failed. Database may have remaining issues.")
            return 1
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
