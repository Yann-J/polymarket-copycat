"""Unit tests for the Polymarket Copy Trading Bot."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from polymarket_copy_trading_bot import (
    PolymarketCopyTradingBot,
    TraderProfile,
    TradeEvent,
    CopyRule,
    LeadFoundCallback,
    TransactionCallback,
)


class TestTraderProfile:
    """Test cases for TraderProfile dataclass."""

    def test_trader_profile_creation(self):
        """Test creating a trader profile with valid data."""
        profile = TraderProfile(
            wallet_address="0x123",
            username="test_trader",
            total_volume=1000.0,
            total_profit=100.0,
            win_rate=0.6,
            avg_trade_size=50.0,
            trade_count=20,
            categories=["Politics"],
            risk_score=5.0,
            is_active=True,
        )

        assert profile.wallet_address == "0x123"
        assert profile.username == "test_trader"
        assert profile.total_volume == 1000.0
        assert profile.is_active is True


class TestTradeEvent:
    """Test cases for TradeEvent dataclass."""

    def test_trade_event_creation(self):
        """Test creating a trade event with valid data."""
        timestamp = datetime.now(timezone.utc)
        event = TradeEvent(
            trader_address="0x123",
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=timestamp,
            market_question="Will X happen?",
            outcome="Yes",
        )

        assert event.trader_address == "0x123"
        assert event.side == "BUY"
        assert event.amount == 100.0
        assert event.timestamp == timestamp


class TestCopyRule:
    """Test cases for CopyRule dataclass."""

    def test_copy_rule_creation(self):
        """Test creating a copy rule with valid data."""
        rule = CopyRule(
            trader_address="0x123",
            copy_percentage=0.1,
            min_copy_amount=10.0,
            max_copy_amount=500.0,
            max_daily_copy=2000.0,
            categories_filter=["Politics"],
            min_market_liquidity=1000.0,
            max_odds_threshold=0.9,
            min_trader_amount=50.0,
            copy_sells=True,
            active=True,
        )

        assert rule.trader_address == "0x123"
        assert rule.copy_percentage == 0.1
        assert rule.active is True


class TestPolymarketCopyTradingBot:
    """Test cases for PolymarketCopyTradingBot class."""

    @pytest.fixture
    def bot(self):
        """Create a bot instance for testing."""
        return PolymarketCopyTradingBot(
            host="https://test.polymarket.com", private_key=None
        )

    def test_bot_initialization(self, bot):
        """Test bot initialization with default parameters."""
        assert bot.host == "https://test.polymarket.com"
        assert bot.private_key is None
        assert bot.chain_id == 137
        assert bot.running is False
        assert len(bot.copy_rules) == 0
        assert len(bot.active_trades) == 0

    def test_add_trader_to_copy(self, bot):
        """Test adding a trader to copy list."""
        trader_address = "0x123"
        bot.add_trader_to_copy(
            trader_address=trader_address, copy_percentage=0.1, min_copy_amount=10.0
        )

        assert trader_address in bot.copy_rules
        rule = bot.copy_rules[trader_address]
        assert rule.copy_percentage == 0.1
        assert rule.min_copy_amount == 10.0
        assert rule.active is True

    def test_add_trader_to_copy_with_defaults(self, bot):
        """Test adding a trader with default parameters."""
        trader_address = "0x456"
        bot.add_trader_to_copy(trader_address=trader_address)

        rule = bot.copy_rules[trader_address]
        assert rule.copy_percentage == 0.1
        assert rule.min_copy_amount == 10.0
        assert rule.max_copy_amount == 500.0
        assert rule.categories_filter == [
            "Politics",
            "Sports",
            "Crypto",
            "Entertainment",
        ]

    def test_should_copy_trade_valid_trade(self, bot):
        """Test should_copy_trade with a valid trade."""
        # Add a trader to copy
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address)

        # Create a valid trade event
        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        # Mock the helper methods
        with patch.object(
            bot, "get_market_category", return_value="Politics"
        ), patch.object(bot, "get_market_liquidity", return_value=5000.0), patch.object(
            bot, "get_daily_copied_amount", return_value=0.0
        ):

            result = bot.should_copy_trade(trade_event, copy_rule)
            assert result is True

    def test_should_copy_trade_insufficient_amount(self, bot):
        """Test should_copy_trade with insufficient trader amount."""
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address, min_trader_amount=200.0)

        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=50.0,  # Below minimum
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]
        result = bot.should_copy_trade(trade_event, copy_rule)
        assert result is False

    def test_should_copy_trade_wrong_category(self, bot):
        """Test should_copy_trade with wrong market category."""
        trader_address = "0x123"
        bot.add_trader_to_copy(
            trader_address=trader_address, categories_filter=["Politics"]
        )

        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        with patch.object(bot, "get_market_category", return_value="Sports"):
            result = bot.should_copy_trade(trade_event, copy_rule)
            assert result is False

    def test_calculate_copy_amount(self, bot):
        """Test calculating copy amount."""
        trader_address = "0x123"
        bot.add_trader_to_copy(
            trader_address=trader_address,
            copy_percentage=0.1,
            min_copy_amount=10.0,
            max_copy_amount=100.0,
        )

        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=500.0,  # 10% = 50.0
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        with patch.object(
            bot, "get_available_balance", return_value=10000.0
        ), patch.object(bot, "get_daily_spent", return_value=0.0):

            amount = bot.calculate_copy_amount(trade_event, copy_rule)
            assert amount == 50.0  # 500 * 0.1

    def test_calculate_copy_amount_with_limits(self, bot):
        """Test calculating copy amount with min/max limits."""
        trader_address = "0x123"
        bot.add_trader_to_copy(
            trader_address=trader_address,
            copy_percentage=0.1,
            min_copy_amount=20.0,
            max_copy_amount=30.0,
        )

        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,  # 10% = 10.0, but min is 20.0
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        with patch.object(
            bot, "get_available_balance", return_value=10000.0
        ), patch.object(bot, "get_daily_spent", return_value=0.0):

            amount = bot.calculate_copy_amount(trade_event, copy_rule)
            assert amount == 20.0  # Min limit applied

    def test_get_market_category(self, bot):
        """Test getting market category."""
        category = bot.get_market_category("test_market_id")
        assert category in [
            "Politics",
            "Sports",
            "Crypto",
            "Entertainment",
            "Economics",
        ]

    def test_get_market_liquidity(self, bot):
        """Test getting market liquidity."""
        liquidity = bot.get_market_liquidity("test_market_id")
        assert 1000 <= liquidity <= 11000  # 1000 + (hash % 10000)

    def test_get_daily_copied_amount(self, bot):
        """Test getting daily copied amount."""
        trader_address = "0x123"
        amount = bot.get_daily_copied_amount(trader_address)
        assert amount == 0.0  # No trades yet

    def test_get_daily_spent(self, bot):
        """Test getting daily spent amount."""
        amount = bot.get_daily_spent()
        assert amount == 0.0  # No trades yet

    def test_get_available_balance(self, bot):
        """Test getting available balance."""
        balance = bot.get_available_balance()
        assert balance == 10000.0  # Demo balance

    def test_get_performance_report(self, bot):
        """Test getting performance report."""
        report = bot.get_performance_report()

        assert "total_copy_trades" in report
        assert "total_volume_copied" in report
        assert "estimated_pnl" in report
        assert "daily_spent" in report
        assert "active_traders_followed" in report
        assert "last_updated" in report

        assert report["total_copy_trades"] == 0
        assert report["total_volume_copied"] == 0.0
        assert report["active_traders_followed"] == 0

    @pytest.mark.asyncio
    async def test_stop_bot(self, bot):
        """Test stopping the bot."""
        bot.running = True
        await bot.stop()
        assert bot.running is False

    def test_set_lead_found_callback(self, bot):
        """Test setting lead found callback."""
        callback = Mock()
        bot.set_lead_found_callback(callback)
        assert bot.lead_found_callback == callback

    def test_set_transaction_callback(self, bot):
        """Test setting transaction callback."""
        callback = Mock()
        bot.set_transaction_callback(callback)
        assert bot.transaction_callback == callback

    def test_lead_found_callback_invocation(self, bot):
        """Test that lead found callback is invoked when a lead is found."""
        callback = Mock()
        bot.set_lead_found_callback(callback)

        # Add a trader to copy
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address)

        # Create a valid trade event
        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        # Mock the helper methods
        with patch.object(
            bot, "get_market_category", return_value="Politics"
        ), patch.object(bot, "get_market_liquidity", return_value=5000.0), patch.object(
            bot, "get_daily_copied_amount", return_value=0.0
        ), patch.object(
            bot, "calculate_copy_amount", return_value=50.0
        ):

            # Process the trade
            bot.process_trader_trade(trade_event)

            # Verify callback was called
            callback.assert_called_once_with(trade_event, copy_rule)

    def test_transaction_callback_invocation(self, bot):
        """Test that transaction callback is invoked when a transaction is made."""
        callback = Mock()
        bot.set_transaction_callback(callback)

        # Add a trader to copy
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address)

        # Create a valid trade event
        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        # Mock the helper methods
        with patch.object(
            bot, "get_market_category", return_value="Politics"
        ), patch.object(bot, "get_market_liquidity", return_value=5000.0), patch.object(
            bot, "get_daily_copied_amount", return_value=0.0
        ), patch.object(
            bot, "calculate_copy_amount", return_value=50.0
        ), patch.object(
            bot, "execute_copy_trade"
        ) as mock_execute:

            # Process the trade
            bot.process_trader_trade(trade_event)

            # Verify execute_copy_trade was called
            mock_execute.assert_called_once_with(trade_event, 50.0)

    def test_callback_error_handling(self, bot):
        """Test that callback errors are handled gracefully."""
        callback = Mock(side_effect=Exception("Callback error"))
        bot.set_lead_found_callback(callback)

        # Add a trader to copy
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address)

        # Create a valid trade event
        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        # Mock the helper methods
        with patch.object(
            bot, "get_market_category", return_value="Politics"
        ), patch.object(bot, "get_market_liquidity", return_value=5000.0), patch.object(
            bot, "get_daily_copied_amount", return_value=0.0
        ), patch.object(
            bot, "calculate_copy_amount", return_value=50.0
        ), patch.object(
            bot, "execute_copy_trade"
        ) as mock_execute:

            # Process the trade - should not raise exception
            bot.process_trader_trade(trade_event)

            # Verify callback was called despite error
            callback.assert_called_once()
            # Verify execute_copy_trade was still called
            mock_execute.assert_called_once_with(trade_event, 50.0)

    def test_bot_initialization_with_callbacks(self):
        """Test bot initialization with callbacks."""
        lead_callback = Mock()
        transaction_callback = Mock()

        bot = PolymarketCopyTradingBot(
            host="https://test.polymarket.com",
            private_key=None,
            lead_found_callback=lead_callback,
            transaction_callback=transaction_callback,
        )

        assert bot.lead_found_callback == lead_callback
        assert bot.transaction_callback == transaction_callback


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def bot(self):
        """Create a bot instance for testing."""
        return PolymarketCopyTradingBot()

    def test_should_copy_trade_no_rule(self, bot):
        """Test should_copy_trade when no copy rule exists."""
        trade_event = TradeEvent(
            trader_address="0x123",
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=100.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = None
        result = bot.should_copy_trade(trade_event, copy_rule)
        assert result is False

    def test_calculate_copy_amount_insufficient_balance(self, bot):
        """Test calculate_copy_amount with insufficient balance."""
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address)

        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=1000.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        with patch.object(
            bot, "get_available_balance", return_value=500.0
        ), patch.object(bot, "get_daily_spent", return_value=0.0):

            amount = bot.calculate_copy_amount(trade_event, copy_rule)
            assert amount == 0.0  # Insufficient balance

    def test_calculate_copy_amount_daily_limit_exceeded(self, bot):
        """Test calculate_copy_amount when daily limit is exceeded."""
        trader_address = "0x123"
        bot.add_trader_to_copy(trader_address=trader_address, max_daily_copy=100.0)

        trade_event = TradeEvent(
            trader_address=trader_address,
            market_id="market_123",
            token_id="token_123",
            side="BUY",
            amount=1000.0,
            price=0.6,
            timestamp=datetime.now(timezone.utc),
            market_question="Test question",
            outcome="Yes",
        )

        copy_rule = bot.copy_rules[trader_address]

        with patch.object(
            bot, "get_available_balance", return_value=10000.0
        ), patch.object(bot, "get_daily_spent", return_value=100.0):

            amount = bot.calculate_copy_amount(trade_event, copy_rule)
            assert amount == 0.0  # Daily limit exceeded
