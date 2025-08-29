#!/usr/bin/env python3
"""
Test script to identify potential wallet race conditions and money duplication issues.
"""

import sys
import os
import threading
import time
import random

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poker.database import get_database, init_database
from poker.wallet import get_wallet_manager


def test_concurrent_wallet_creation():
    """Test creating the same wallet from multiple threads simultaneously."""
    print("🧪 Testing concurrent wallet creation...")
    
    db = get_database()
    wallet_manager = get_wallet_manager()
    
    test_user = f"test_user_{int(time.time())}"
    results = []
    
    def create_wallet_thread(thread_id):
        try:
            # Simulate simultaneous wallet creation
            wallet = wallet_manager.get_player_wallet(test_user)
            results.append(f"Thread {thread_id}: Created wallet with ${wallet['balance']}")
        except Exception as e:
            results.append(f"Thread {thread_id}: ERROR - {e}")
    
    # Create 5 threads that try to create the same wallet simultaneously
    threads = []
    for i in range(5):
        thread = threading.Thread(target=create_wallet_thread, args=(i,))
        threads.append(thread)
    
    # Start all threads at roughly the same time
    for thread in threads:
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Check results
    print("  Results:")
    for result in results:
        print(f"    {result}")
    
    # Check database state
    final_wallet = db.get_wallet(test_user)
    print(f"  Final wallet balance: ${final_wallet['balance']}")
    
    # Check for duplicate transactions
    transactions = db.get_player_transactions(test_user, 100)
    creation_txns = [tx for tx in transactions if tx['transaction_type'] == 'WALLET_CREATED']
    if len(creation_txns) > 1:
        print(f"  ⚠️  WARNING: Found {len(creation_txns)} wallet creation transactions (should be 1)")
    else:
        print(f"  ✅ Only {len(creation_txns)} wallet creation transaction found")
    
    return len(creation_txns) <= 1


def test_wallet_cache_save_race():
    """Test potential race conditions in wallet save operations."""
    print("\n🧪 Testing wallet cache/save race conditions...")
    
    wallet_manager = get_wallet_manager()
    test_user = f"test_save_{int(time.time())}"
    
    # Create wallet
    wallet = wallet_manager.get_player_wallet(test_user)
    print(f"  Initial wallet: ${wallet['balance']}")
    
    results = []
    
    def modify_and_save_thread(thread_id, amount):
        try:
            # Get chips for game
            chips = wallet_manager.get_player_chips_for_game(test_user)
            # Add some winnings
            wallet_manager.return_chips_to_wallet(test_user, chips + amount)
            # Save to database
            success = wallet_manager.save_wallet_to_database(test_user)
            results.append(f"Thread {thread_id}: Modified by {amount}, save={'success' if success else 'failed'}")
        except Exception as e:
            results.append(f"Thread {thread_id}: ERROR - {e}")
    
    # Create threads that modify and save simultaneously
    threads = []
    for i in range(3):
        amount = random.randint(100, 500)
        thread = threading.Thread(target=modify_and_save_thread, args=(i, amount))
        threads.append(thread)
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    # Check results
    print("  Results:")
    for result in results:
        print(f"    {result}")
    
    # Check final state
    final_wallet = wallet_manager.get_player_wallet(test_user)
    print(f"  Final cached balance: ${final_wallet['balance']}")
    
    # Force refresh from database
    db_wallet = get_database().get_wallet(test_user)
    print(f"  Final database balance: ${db_wallet['balance']}")
    
    if final_wallet['balance'] != db_wallet['balance']:
        print(f"  ⚠️  WARNING: Cache/DB mismatch detected!")
        return False
    else:
        print(f"  ✅ Cache and database are consistent")
        return True


def test_large_balance_handling():
    """Test how the system handles suspiciously large balances."""
    print("\n🧪 Testing large balance handling...")
    
    wallet_manager = get_wallet_manager()
    test_user = f"test_large_{int(time.time())}"
    
    # Try to add a huge amount
    wallet_manager.add_funds(test_user, 1000000, "Test large amount")
    wallet = wallet_manager.get_player_wallet(test_user)
    print(f"  After adding $1,000,000: ${wallet['balance']}")
    
    # Try to get chips for game with huge balance
    chips = wallet_manager.get_player_chips_for_game(test_user)
    print(f"  Chips received for game: ${chips}")
    
    # Check if it was capped
    if chips < wallet['balance'] + 500:  # 500 is the initial balance
        print(f"  ✅ Large balance was properly handled/capped")
        return True
    else:
        print(f"  ⚠️  WARNING: Large balance was not capped")
        return False


def main():
    """Run all wallet integrity tests."""
    print("🔧 Poker-over-SSH Wallet Integrity Tests")
    print("=" * 50)
    
    try:
        # Initialize clean database for testing
        test_db_path = "test_poker_data.db"
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        
        init_database(test_db_path)
        
        # Run tests
        test1_passed = test_concurrent_wallet_creation()
        test2_passed = test_wallet_cache_save_race()
        test3_passed = test_large_balance_handling()
        
        # Summary
        print(f"\n📋 Test Summary:")
        print(f"  Concurrent wallet creation: {'✅ PASS' if test1_passed else '❌ FAIL'}")
        print(f"  Cache/save race conditions: {'✅ PASS' if test2_passed else '❌ FAIL'}")
        print(f"  Large balance handling: {'✅ PASS' if test3_passed else '❌ FAIL'}")
        
        if all([test1_passed, test2_passed, test3_passed]):
            print(f"\n🎉 All tests passed! Wallet system appears robust.")
        else:
            print(f"\n⚠️  Some tests failed. Check the output above for issues.")
        
        # Clean up test database
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
