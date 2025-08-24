"""
Poker AI using OpenAI-compatible API for decision making.
"""

import asyncio
import json
import os
import random
from typing import Any, Dict, Optional, Callable, Awaitable

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class PokerAI:
    def __init__(self, player):
        self.player = player
        self.client = None
        self.thinking_callback = None  # Callback to notify when AI is thinking
        self._setup_client()

    def _setup_client(self):
        """Setup OpenAI client with custom endpoint"""
        if not AsyncOpenAI:
            print("OpenAI package not installed, falling back to simple AI")
            return
        
        api_key = os.getenv('AI_API_KEY')
        base_url = os.getenv('AI_API_BASE_URL')
        
        if not api_key or not base_url:
            print("AI_API_KEY or AI_API_BASE_URL not configured, falling back to simple AI")
            return
            
        try:
            timeout = float(os.getenv('AI_TIMEOUT', '5'))  # Reduced from 30 to 5 seconds
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout
            )
            print(f"AI client configured with endpoint: {base_url}")
        except Exception as e:
            print(f"Failed to setup AI client: {e}, falling back to simple AI")
            self.client = None

    async def test_connection(self) -> bool:
        """Test if the AI endpoint is accessible"""
        if not self.client:
            return False
        
        try:
            # Simple test request
            response = await self.client.chat.completions.create(
                model=os.getenv('AI_MODEL', 'llama-3.1-8b-instant'),
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return True
        except Exception as e:
            error_msg = str(e)
            if "cloudflare" in error_msg.lower() or "blocked" in error_msg.lower():
                print("🛡️  AI endpoint is blocked by Cloudflare")
            elif "timeout" in error_msg.lower():
                print("⏱️  AI endpoint timed out")
            elif "connection" in error_msg.lower():
                print("🔌 Cannot connect to AI endpoint")
            else:
                print(f"❌ AI test failed: {error_msg[:100]}...")
            return False

    async def decide_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Make a poker decision using AI or fallback to simple logic"""
        # Notify that AI is starting to think
        if self.thinking_callback and callable(self.thinking_callback):
            try:
                result = self.thinking_callback(self.player.name, True)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Don't let callback errors break the decision process
        
        try:
            if self.client:
                try:
                    return await self._ai_decision(game_state)
                except Exception as e:
                    print(f"AI decision failed: {e}, using fallback")
            
            return await self._simple_decision(game_state)
        finally:
            # Notify that AI is done thinking
            if self.thinking_callback and callable(self.thinking_callback):
                try:
                    result = self.thinking_callback(self.player.name, False)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass  # Don't let callback errors break the decision process

    async def _ai_decision(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Use AI to make poker decision"""
        if not self.client:
            return await self._simple_decision(game_state)
            
        # Prepare the game state for the AI
        prompt = self._create_poker_prompt(game_state)
        
        # Add a small delay to simulate thinking (reduced)
        await asyncio.sleep(random.uniform(0.2, 0.6))
        
        try:
            model = os.getenv('AI_MODEL', 'llama-3.1-8b-instant')
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert poker player. Analyze the game state and make the best decision. Respond with valid JSON containing 'action' (fold/call/raise) and 'amount' (0 for fold/call, positive for raise)."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            # Parse the AI response
            content = response.choices[0].message.content
            if not content:
                print("AI returned empty response, using fallback")
                return await self._simple_decision(game_state)
                
            content = content.strip()
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                if '{' in content and '}' in content:
                    start = content.find('{')
                    end = content.rfind('}') + 1
                    json_str = content[start:end]
                    decision = json.loads(json_str)
                else:
                    # Fallback: parse text response
                    decision = self._parse_text_decision(content)
                
                # Validate and sanitize the decision
                return self._validate_decision(decision, game_state)
                
            except (json.JSONDecodeError, KeyError):
                # If JSON parsing fails, try to interpret the text
                return self._parse_text_decision(content, game_state)
                
        except Exception as e:
            error_msg = str(e)
            
            # Detect Cloudflare blocks
            if "cloudflare" in error_msg.lower() or "blocked" in error_msg.lower() or "<!DOCTYPE html>" in error_msg:
                print(f"🛡️  AI endpoint blocked by Cloudflare. Using smart fallback AI.")
                print("   💡 Tip: Consider using a different AI endpoint or direct OpenAI API.")
            elif "timeout" in error_msg.lower():
                print(f"⏱️  AI request timed out. Using fallback AI.")
            elif "connection" in error_msg.lower():
                print(f"🔌 AI connection failed. Using fallback AI.")
            else:
                print(f"❌ AI API call failed: {error_msg[:100]}...")
            
            return await self._simple_decision(game_state)

    def _create_poker_prompt(self, game_state: Dict[str, Any]) -> str:
        """Create a detailed prompt for the AI"""
        community = game_state.get('community', [])
        bets = game_state.get('bets', {})
        pot = game_state.get('pot', 0)
        players = game_state.get('players', [])
        
        # Format cards nicely
        hand_str = self._format_cards(self.player.hand)
        community_str = self._format_cards(community) if community else "None"
        
        # Calculate betting info
        current_bet = max(bets.values()) if bets else 0
        my_bet = bets.get(self.player.name, 0)
        call_amount = max(current_bet - my_bet, 0)
        
        prompt = f"""
POKER GAME STATE:
- Your hand: {hand_str}
- Community cards: {community_str}
- Your chips: {self.player.chips}
- Pot size: {pot}
- Current highest bet: {current_bet}
- Your current bet: {my_bet}
- Amount to call: {call_amount}
- Number of players: {len(players)}

BETTING ROUND: {"Preflop" if not community else f"Post-flop ({len(community)} cards)"}

Your options:
1. FOLD - Give up your hand (amount: 0)
2. CALL - Match the current bet (amount: {call_amount})
3. RAISE - Increase the bet (amount: more than {call_amount})

Consider:
- Hand strength
- Position
- Pot odds
- Opponent behavior
- Stack size

Respond with JSON: {{"action": "fold/call/raise", "amount": number}}
"""
        return prompt

    def _format_cards(self, cards) -> str:
        """Format cards for display"""
        if not cards:
            return "None"
        
        suits = {'s': '♠', 'h': '♥', 'd': '♦', 'c': '♣'}
        ranks = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
        
        formatted = []
        for rank, suit in cards:
            rank_str = ranks.get(rank, str(rank))
            suit_str = suits.get(suit, suit)
            formatted.append(f"{rank_str}{suit_str}")
        
        return ", ".join(formatted)

    def _parse_text_decision(self, content: str, game_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Parse text response to extract decision"""
        content_lower = content.lower()
        
        if 'fold' in content_lower:
            return {'action': 'fold', 'amount': 0}
        elif 'raise' in content_lower:
            # Try to extract raise amount
            import re
            numbers = re.findall(r'\d+', content)
            if numbers:
                amount = int(numbers[-1])  # Take the last number found
                return {'action': 'raise', 'amount': amount}
            else:
                # Default small raise
                return {'action': 'raise', 'amount': 10}
        else:
            # Default to call
            return {'action': 'call', 'amount': 0}

    def _validate_decision(self, decision: Dict[str, Any], game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize the AI decision"""
        action = decision.get('action', 'fold').lower()
        amount = decision.get('amount', 0)
        
        # Ensure valid action
        if action not in ['fold', 'call', 'raise']:
            action = 'call'
        
        # Calculate betting constraints
        bets = game_state.get('bets', {})
        current_bet = max(bets.values()) if bets else 0
        my_bet = bets.get(self.player.name, 0)
        call_amount = max(current_bet - my_bet, 0)
        
        # Validate amounts
        if action == 'fold':
            amount = 0
        elif action == 'call':
            amount = call_amount
        elif action == 'raise':
            # Ensure raise is at least a call + minimum raise
            min_raise = call_amount + 10
            if amount < min_raise:
                amount = min_raise
            # Ensure we have enough chips
            if amount > self.player.chips:
                if call_amount <= self.player.chips:
                    action = 'call'
                    amount = call_amount
                else:
                    action = 'fold'
                    amount = 0
        
        return {'action': action, 'amount': amount}

    async def _simple_decision(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback simple AI logic with realistic thinking time"""
        # Shorter, more human-like thinking delay
        community = game_state.get('community', [])
        bets = game_state.get('bets', {})
        pot = game_state.get('pot', 0)
        
        # Calculate thinking time based on complexity (shorter than before)
        base_delay = 0.8  # Reduced from 1.0
        
        # More community cards = slightly more thinking
        if community:
            base_delay += len(community) * 0.1  # Reduced from 0.3
        
        # Bigger pot = a bit more consideration
        if pot > 100:
            base_delay += 0.2  # Reduced from 0.5
        
        # If there's betting action, think a bit longer
        if bets and max(bets.values()) > 0:
            base_delay += 0.2  # Reduced from 0.4
        
        # Add some randomness to make it feel natural
        thinking_delay = random.uniform(base_delay * 0.8, base_delay * 1.2)
        thinking_delay = min(thinking_delay, 2.5)  # Cap at 2.5 seconds instead of 4
        
        await asyncio.sleep(thinking_delay)
        
        # game_state contains 'community', 'pot', 'bets', 'players'
        chips = self.player.chips
        
        # Calculate how much we need to call
        current_bet = max(bets.values()) if bets else 0
        my_bet = bets.get(self.player.name, 0)
        call_amount = max(current_bet - my_bet, 0)
        
        # If nobody has bet (everyone checked), prefer to check rather than folding.
        # Returning a 'call' with amount 0 represents a check in this codebase.
        if call_amount == 0:
            return {'action': 'call', 'amount': 0}

        # If we don't have enough money to call, fold
        if call_amount > chips:
            return {'action': 'fold', 'amount': 0}

        # Very naive rules
        if not community:
            # preflop
            ranks = sorted([c[0] for c in self.player.hand], reverse=True)
            # pocket pair or at least one high card -> call
            if ranks[0] == ranks[1] or ranks[0] >= 11 or ranks[1] >= 11:
                return {'action': 'call', 'amount': call_amount}
            return {'action': 'fold', 'amount': 0}

        # Postflop: if we have any pair with community, stay in
        my_ranks = [c[0] for c in self.player.hand]
        comm_ranks = [c[0] for c in community]
        if any(r in comm_ranks for r in my_ranks):
            return {'action': 'call', 'amount': call_amount}

        # If low chips, conserve
        if chips < 50:
            return {'action': 'fold', 'amount': 0}

        # default to check/call
        return {'action': 'call', 'amount': call_amount}
