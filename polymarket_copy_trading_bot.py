# -*- coding: utf-8 -*-
"""Polymarket Copy Trading Bot.

A sophisticated copy trading bot that monitors successful traders on Polymarket
and automatically replicates their trading strategies with configurable risk
management.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Any, Callable, Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import SELL

# Bot configuration constants
DEFAULT_MAX_DAILY_BUDGET = 5000.0
DEFAULT_MIN_ACCOUNT_BALANCE = 1000.0
DEFAULT_MAX_CONCURRENT_COPIES = 20
DEFAULT_MONITORING_INTERVAL = 30  # seconds
DEFAULT_TRADE_CHECK_INTERVAL = 60  # seconds
DEFAULT_RISK_CHECK_INTERVAL = 300  # seconds
DEFAULT_STATS_UPDATE_INTERVAL = 3600  # seconds
DEFAULT_TRADE_FILL_TIMEOUT = 300  # seconds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("polymarket_copy_trading.log"),
        logging.StreamHandler(),
    ],
)


@dataclass
class TraderProfile:
    """Profile of a trader to copy.

    Attributes:
        wallet_address: The trader's wallet address.
        username: The trader's display name.
        total_volume: Total trading volume in USD.
        total_profit: Total profit/loss in USD.
        win_rate: Win rate as a decimal (0.0-1.0).
        avg_trade_size: Average trade size in USD.
        trade_count: Total number of trades.
        categories: List of market categories the trader focuses on.
        risk_score: Risk score from 1-10 (10 = highest risk).
        is_active: Whether the trader is currently active.
    """

    wallet_address: str
    username: str
    total_volume: float
    total_profit: float
    win_rate: float
    avg_trade_size: float
    trade_count: int
    categories: List[str]
    risk_score: float
    is_active: bool


@dataclass
class TradeEvent:
    """Individual trade event from a followed trader.

    Attributes:
        trader_address: The trader's wallet address.
        market_id: Unique identifier for the market.
        token_id: Token identifier for the specific outcome.
        side: Trade side ("BUY" or "SELL").
        amount: Trade amount in USD.
        price: Price per share.
        timestamp: When the trade occurred.
        market_question: The market question text.
        outcome: The specific outcome being traded.
    """

    trader_address: str
    market_id: str
    token_id: str
    side: str
    amount: float
    price: float
    timestamp: datetime
    market_question: str
    outcome: str


@dataclass
class CopyRule:
    """Rules for copying a specific trader.

    Attributes:
        trader_address: The trader's wallet address.
        copy_percentage: Percentage of trader's trade size to copy (0.1 = 10%).
        min_copy_amount: Minimum amount to copy in USD.
        max_copy_amount: Maximum amount to copy in USD.
        max_daily_copy: Maximum daily copy amount in USD.
        categories_filter: Only copy trades in these categories.
        min_market_liquidity: Minimum market liquidity required.
        max_odds_threshold: Don't copy if odds exceed this threshold.
        min_trader_amount: Only copy if trader bets at least this amount.
        copy_sells: Whether to copy sell orders.
        active: Whether this copy rule is active.
    """

    trader_address: str
    copy_percentage: float
    min_copy_amount: float
    max_copy_amount: float
    max_daily_copy: float
    categories_filter: List[str]
    min_market_liquidity: float
    max_odds_threshold: float
    min_trader_amount: float
    copy_sells: bool
    active: bool


# Callback function type definitions
LeadFoundCallback = Callable[[TradeEvent, CopyRule], None]
TransactionCallback = Callable[[Dict[str, Any], str], None]


class PolymarketCopyTradingBot:
    """Advanced copy trading bot for Polymarket.

    Monitors successful traders and automatically replicates their trading
    strategies with configurable risk management and filtering.

    Features:
        - Multi-trader monitoring and copying
        - Advanced filtering and risk management
        - Real-time trade execution
        - Performance tracking and analytics
        - Trader ranking and discovery
        - Custom callback support for events

    Attributes:
        host: Polymarket CLOB API host URL.
        private_key: Private key for trading (None for read-only mode).
        funder_address: Funder address for proxy wallet.
        chain_id: Blockchain chain ID (137 for Polygon).
        signature_type: Signature type for orders.
        client: CLOB client instance.
        copy_rules: Dictionary of copy rules by trader address.
        active_trades: List of currently active copy trades.
        trade_history: List of completed trade events.
        trader_profiles: Dictionary of trader profiles.
        max_daily_budget: Maximum daily trading budget.
        min_account_balance: Minimum balance to maintain.
        max_concurrent_copies: Maximum concurrent copy trades.
        running: Whether the bot is currently running.
        logger: Logger instance for the bot.
        lead_found_callback: Optional callback for when a lead is found.
        transaction_callback: Optional callback for when transactions are made.
    """

    def __init__(
        self,
        host: str = "https://clob.polymarket.com",
        private_key: str = None,
        funder_address: str = None,
        chain_id: int = 137,
        signature_type: int = 1,
        lead_found_callback: Optional[LeadFoundCallback] = None,
        transaction_callback: Optional[TransactionCallback] = None,
    ) -> None:
        """Initialize the copy trading bot.

        Args:
            host: Polymarket CLOB API host URL.
            private_key: Private key for trading (None for read-only mode).
            funder_address: Funder address for proxy wallet.
            chain_id: Blockchain chain ID (137 for Polygon).
            signature_type: Signature type for orders.
            lead_found_callback: Optional callback function called when a
                lead is found.
            transaction_callback: Optional callback function called when
                transactions are made.
        """

        self.host = host
        self.private_key = private_key
        self.funder_address = funder_address
        self.chain_id = chain_id
        self.signature_type = signature_type
        self.lead_found_callback = lead_found_callback
        self.transaction_callback = transaction_callback

        # Initialize CLOB client
        self._initialize_clob_client()

        # Initialize bot state
        self._initialize_bot_state()

        self.logger = logging.getLogger(__name__)

    def _initialize_clob_client(self) -> None:
        """Initialize the CLOB client for trading.

        Sets up the client with appropriate credentials if private key
        is provided, otherwise creates a read-only client.
        """
        if self.private_key:
            self.client = ClobClient(
                host=self.host,
                key=self.private_key,
                chain_id=self.chain_id,
                signature_type=self.signature_type,
                funder=self.funder_address,
            )
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
        else:
            self.client = ClobClient(self.host)

    def _initialize_bot_state(self) -> None:
        """Initialize bot state variables.

        Sets up all the data structures and configuration
        needed for the bot to operate.
        """
        # Copy trading configuration
        self.copy_rules: Dict[str, CopyRule] = {}
        self.active_trades: List[Dict] = []
        self.trade_history: List[TradeEvent] = []
        self.trader_profiles: Dict[str, TraderProfile] = {}

        # Bot settings
        self.max_daily_budget = DEFAULT_MAX_DAILY_BUDGET
        self.min_account_balance = DEFAULT_MIN_ACCOUNT_BALANCE
        self.max_concurrent_copies = DEFAULT_MAX_CONCURRENT_COPIES
        self.running = False

    def add_trader_to_copy(
        self,
        trader_address: str,
        copy_percentage: float = 0.1,
        min_copy_amount: float = 10,
        max_copy_amount: float = 500,
        max_daily_copy: float = 2000,
        categories_filter: List[str] = None,
        min_market_liquidity: float = 1000,
        max_odds_threshold: float = 0.9,
        min_trader_amount: float = 50,
        copy_sells: bool = True,
    ) -> None:
        """Add a trader to copy with specific rules.

        Args:
            trader_address: The trader's wallet address.
            copy_percentage: Percentage of trader's trade size to copy.
            min_copy_amount: Minimum amount to copy in USD.
            max_copy_amount: Maximum amount to copy in USD.
            max_daily_copy: Maximum daily copy amount in USD.
            categories_filter: Only copy trades in these categories.
            min_market_liquidity: Minimum market liquidity required.
            max_odds_threshold: Don't copy if odds exceed this threshold.
            min_trader_amount: Only copy if trader bets at least this amount.
            copy_sells: Whether to copy sell orders.
        """

        # if categories_filter is None:
        #     categories_filter = ["Politics", "Sports", "Crypto", "Entertainment"]

        copy_rule = CopyRule(
            trader_address=trader_address,
            copy_percentage=copy_percentage,
            min_copy_amount=min_copy_amount,
            max_copy_amount=max_copy_amount,
            max_daily_copy=max_daily_copy,
            categories_filter=categories_filter,
            min_market_liquidity=min_market_liquidity,
            max_odds_threshold=max_odds_threshold,
            min_trader_amount=min_trader_amount,
            copy_sells=copy_sells,
            active=True,
        )

        self.copy_rules[trader_address] = copy_rule
        self.logger.info("Added trader %s to copy list", trader_address)

    def set_lead_found_callback(self, callback: LeadFoundCallback) -> None:
        """Set the callback function for when a lead is found.

        Args:
            callback: Function to call when a lead is found.
        """
        self.lead_found_callback = callback
        self.logger.info("Lead found callback set")

    def set_transaction_callback(self, callback: TransactionCallback) -> None:
        """Set the callback function for when transactions are made.

        Args:
            callback: Function to call when transactions are made.
        """
        self.transaction_callback = callback
        self.logger.info("Transaction callback set")

    async def monitor_trader_activity(self, trader_address: str) -> None:
        """Monitor a specific trader's activity via blockchain/API.

        Args:
            trader_address: The trader's wallet address to monitor.
        """
        try:
            # In a real implementation, this would:
            # 1. Monitor blockchain transactions for the wallet
            # 2. Parse Polymarket trade events
            # 3. Get market details and trade information
            # 4. Trigger copy trades based on rules

            # For demo, we'll simulate getting trader activity
            self.logger.info("Monitoring trader: %s", trader_address)

            while self.running:
                try:
                    # Simulate checking for new trades
                    # In reality, you'd query:
                    # - Polygon blockchain events
                    # - Polymarket API for user trades
                    # - WebSocket feeds for real-time updates

                    await asyncio.sleep(DEFAULT_MONITORING_INTERVAL)

                except Exception as e:
                    self.logger.error("Error monitoring %s: %s", trader_address, e)
                    await asyncio.sleep(60)

        except Exception as e:
            self.logger.error("Fatal error monitoring %s: %s", trader_address, e)

    async def process_trader_trade(self, trade_event: TradeEvent) -> None:
        """Process a trade from a followed trader and decide if to copy.

        Args:
            trade_event: The trade event to process.
        """
        try:
            copy_rule = self.copy_rules.get(trade_event.trader_address)
            if not copy_rule or not copy_rule.active:
                return

            # Check if trade meets copy criteria
            if not self.should_copy_trade(trade_event, copy_rule):
                return

            # Calculate copy amount
            copy_amount = self.calculate_copy_amount(trade_event, copy_rule)
            if copy_amount <= 0:
                return

            # Invoke lead found callback if provided
            if self.lead_found_callback:
                try:
                    self.lead_found_callback(trade_event, copy_rule)
                except Exception as e:
                    self.logger.error("Error in lead found callback: %s", e)

            # Execute copy trade
            await self.execute_copy_trade(trade_event, copy_amount)

        except Exception as e:
            self.logger.error("Error processing trade: %s", e)

    def should_copy_trade(self, trade_event: TradeEvent, copy_rule: CopyRule) -> bool:
        """Determine if a trade should be copied based on rules.

        Args:
            trade_event: The trade event to evaluate.
            copy_rule: The copy rule to apply.

        Returns:
            True if the trade should be copied, False otherwise.
        """
        try:
            # Check minimum trader amount
            if trade_event.amount < copy_rule.min_trader_amount:
                self.logger.debug(
                    "Trade amount $%.2f below minimum $%.2f",
                    trade_event.amount,
                    copy_rule.min_trader_amount,
                )
                return False

            # Check category filter
            market_category = self.get_market_category(trade_event.market_id)
            if market_category not in copy_rule.categories_filter:
                self.logger.debug("Market category %s not in filter", market_category)
                return False

            # Check odds threshold (don't copy very likely outcomes)
            if trade_event.price > copy_rule.max_odds_threshold:
                self.logger.debug(
                    "Odds %.2f above threshold %.2f",
                    trade_event.price,
                    copy_rule.max_odds_threshold,
                )
                return False

            # Check market liquidity
            market_liquidity = self.get_market_liquidity(trade_event.market_id)
            if market_liquidity < copy_rule.min_market_liquidity:
                self.logger.debug(
                    "Market liquidity $%.2f below minimum $%.2f",
                    market_liquidity,
                    copy_rule.min_market_liquidity,
                )
                return False

            # Check daily copy limit
            daily_copied = self.get_daily_copied_amount(trade_event.trader_address)
            if daily_copied >= copy_rule.max_daily_copy:
                self.logger.debug("Daily copy limit reached: $%.2f", daily_copied)
                return False

            # Check if we should copy sells
            if trade_event.side == SELL and not copy_rule.copy_sells:
                self.logger.debug("Sell trade ignored due to copy_sells=False")
                return False

            return True

        except Exception as e:
            self.logger.error("Error checking copy criteria: %s", e)
            return False

    def calculate_copy_amount(
        self, trade_event: TradeEvent, copy_rule: CopyRule
    ) -> float:
        """Calculate the amount to copy based on rules.

        Args:
            trade_event: The trade event to calculate copy amount for.
            copy_rule: The copy rule to apply.

        Returns:
            The amount to copy in USD.
        """
        try:
            # Base copy amount (percentage of original trade)
            base_amount = trade_event.amount * copy_rule.copy_percentage

            # Apply min/max limits
            copy_amount = max(
                copy_rule.min_copy_amount, min(copy_rule.max_copy_amount, base_amount)
            )

            # Check account balance
            available_balance = self.get_available_balance()
            if copy_amount > available_balance - self.min_account_balance:
                copy_amount = max(0, available_balance - self.min_account_balance)

            # Check daily budget
            daily_spent = self.get_daily_spent()
            if daily_spent + copy_amount > self.max_daily_budget:
                copy_amount = max(0, self.max_daily_budget - daily_spent)

            return copy_amount

        except Exception as e:
            self.logger.error("Error calculating copy amount: %s", e)
            return 0

    async def execute_copy_trade(
        self, trade_event: TradeEvent, copy_amount: float
    ) -> None:
        """Execute the copy trade.

        Args:
            trade_event: The trade event to copy.
            copy_amount: The amount to copy in USD.
        """
        try:
            if not self.private_key:
                self.logger.warning("Cannot execute trades in read-only mode")
                return

            # Get current market price
            current_price = self.client.get_midpoint(trade_event.token_id)
            if not current_price:
                self.logger.error("Could not get price for %s", trade_event.token_id)
                return

            # Calculate shares to buy
            shares = copy_amount / current_price

            # Create order
            order_args = OrderArgs(
                token_id=trade_event.token_id,
                price=current_price,
                size=shares,
                side=trade_event.side,
            )

            # Sign and submit order
            signed_order = self.client.create_order(order_args)
            response = self.client.post_order(signed_order, OrderType.GTC)

            if response.get("success"):
                # Record the copy trade
                copy_trade = {
                    "original_trader": trade_event.trader_address,
                    "market_id": trade_event.market_id,
                    "token_id": trade_event.token_id,
                    "side": trade_event.side,
                    "copy_amount": copy_amount,
                    "shares": shares,
                    "price": current_price,
                    "order_id": response.get("order_id"),
                    "timestamp": datetime.now(timezone.utc),
                    "status": "pending",
                }

                self.active_trades.append(copy_trade)

                # Invoke transaction callback if provided
                if self.transaction_callback:
                    try:
                        self.transaction_callback(copy_trade, "executed")
                    except Exception as e:
                        self.logger.error("Error in transaction callback: %s", e)

                self.logger.info(
                    "Copy trade executed: $%.2f following %s in market %s",
                    copy_amount,
                    trade_event.trader_address,
                    trade_event.market_question,
                )
            else:
                self.logger.error("Failed to execute copy trade: %s", response)

        except Exception as e:
            self.logger.error("Error executing copy trade: %s", e)

    def get_market_category(self, market_id: str) -> str:
        """Get the category of a market"""
        try:
            # In real implementation, query market details from API
            # For demo, return random category
            categories = ["Politics", "Sports", "Crypto", "Entertainment", "Economics"]
            return categories[hash(market_id) % len(categories)]
        except Exception:
            return "Unknown"

    def get_market_liquidity(self, market_id: str) -> float:
        """Get the liquidity of a market"""
        try:
            # In real implementation, calculate from order book depth
            # For demo, return simulated liquidity
            return 1000 + (hash(market_id) % 10000)
        except Exception:
            return 0

    def get_daily_copied_amount(self, trader_address: str) -> float:
        """Get amount copied from a trader today"""
        try:
            today = datetime.now(timezone.utc).date()
            daily_amount = 0

            for trade in self.active_trades:
                if (
                    trade["original_trader"] == trader_address
                    and trade["timestamp"].date() == today
                ):
                    daily_amount += trade["copy_amount"]

            return daily_amount
        except Exception:
            return 0

    def get_daily_spent(self) -> float:
        """Get total amount spent today across all copy trades"""
        try:
            today = datetime.now(timezone.utc).date()
            daily_spent = 0

            for trade in self.active_trades:
                if trade["timestamp"].date() == today:
                    daily_spent += trade["copy_amount"]

            return daily_spent
        except Exception:
            return 0

    def get_available_balance(self) -> float:
        """Get available account balance"""
        try:
            # In real implementation, query actual balance
            # For demo, return simulated balance
            return 10000  # $10,000 demo balance
        except Exception:
            return 0

    async def start(self) -> None:
        """Start the copy trading bot.

        Initializes monitoring tasks for all configured traders
        and starts the main bot management tasks.
        """
        self.logger.info("Starting Polymarket Copy Trading Bot...")
        self.running = True

        # Start monitoring tasks for each trader
        monitoring_tasks = []
        for trader_address in self.copy_rules.keys():
            task = asyncio.create_task(self.monitor_trader_activity(trader_address))
            monitoring_tasks.append(task)

        # Start other management tasks
        management_tasks = [
            asyncio.create_task(self.manage_active_trades()),
            asyncio.create_task(self.update_trader_stats()),
            asyncio.create_task(self.risk_monitoring()),
        ]

        # Run all tasks with proper KeyboardInterrupt handling
        try:
            await asyncio.gather(*monitoring_tasks, *management_tasks)
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received, stopping bot...")
            self.running = False
            # Cancel all tasks
            all_tasks = monitoring_tasks + management_tasks
            for task in all_tasks:
                if not task.done():
                    task.cancel()
            # Wait for tasks to complete cancellation
            await asyncio.gather(*all_tasks, return_exceptions=True)
            raise

    async def manage_active_trades(self) -> None:
        """Manage active copy trades.

        Monitors the status of active trades and updates their
        status as they get filled or expire.
        """
        while self.running:
            try:
                # Check status of active trades and update
                for trade in self.active_trades:
                    if trade["status"] == "pending":
                        # In real implementation, check order status
                        # For demo, mark as filled after some time
                        age = (
                            datetime.now(timezone.utc) - trade["timestamp"]
                        ).total_seconds()
                        if age > DEFAULT_TRADE_FILL_TIMEOUT:
                            trade["status"] = "filled"

                            # Invoke transaction callback if provided
                            if self.transaction_callback:
                                try:
                                    self.transaction_callback(trade, "filled")
                                except Exception as e:
                                    self.logger.error(
                                        "Error in transaction callback: %s", e
                                    )

                            self.logger.info("Copy trade filled: %s", trade["order_id"])

                await asyncio.sleep(DEFAULT_TRADE_CHECK_INTERVAL)

            except Exception as e:
                self.logger.error("Error managing trades: %s", e)
                await asyncio.sleep(60)

    async def update_trader_stats(self) -> None:
        """Update statistics for followed traders.

        Periodically updates trader performance metrics including
        win rate, average trade size, and profit trends.
        """
        while self.running:
            try:
                # Update trader performance metrics
                for _ in self.copy_rules.keys():
                    # In real implementation, calculate:
                    # - Recent win rate
                    # - Average trade size
                    # - Profit trends
                    # - Category performance
                    pass

                await asyncio.sleep(DEFAULT_STATS_UPDATE_INTERVAL)

            except Exception as e:
                self.logger.error("Error updating trader stats: %s", e)
                await asyncio.sleep(DEFAULT_STATS_UPDATE_INTERVAL)

    async def risk_monitoring(self) -> None:
        """Monitor risk metrics and exposure.

        Continuously monitors risk metrics including total exposure,
        account balance, and daily spending limits.
        """
        while self.running:
            try:
                # Calculate current exposure
                total_exposure = sum(
                    trade["copy_amount"]
                    for trade in self.active_trades
                    if trade["status"] in ["pending", "filled"]
                )

                # Check if exposure is too high
                if total_exposure > self.max_daily_budget * 0.8:
                    self.logger.warning("High exposure detected: $%.2f", total_exposure)

                # Check account balance
                balance = self.get_available_balance()
                if balance < self.min_account_balance:
                    self.logger.warning("Low balance: $%.2f", balance)

                await asyncio.sleep(DEFAULT_RISK_CHECK_INTERVAL)

            except Exception as e:
                self.logger.error("Error in risk monitoring: %s", e)
                await asyncio.sleep(DEFAULT_RISK_CHECK_INTERVAL)

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report.

        Returns:
            A dictionary containing performance metrics including
            total trades, volume, P&L, and daily spending.
        """
        try:
            total_trades = len(self.active_trades)
            total_volume = sum(trade["copy_amount"] for trade in self.active_trades)

            # Calculate P&L (simplified)
            total_pnl = 0  # Would calculate based on current vs entry prices

            daily_spent = self.get_daily_spent()

            return {
                "total_copy_trades": total_trades,
                "total_volume_copied": total_volume,
                "estimated_pnl": total_pnl,
                "daily_spent": daily_spent,
                "daily_budget_remaining": (self.max_daily_budget - daily_spent),
                "active_traders_followed": len(
                    [r for r in self.copy_rules.values() if r.active]
                ),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            self.logger.error("Error generating report: %s", e)
            return {}

    async def stop(self) -> None:
        """Stop the bot.

        Gracefully stops all monitoring tasks and updates
        the bot state to indicate it is no longer running.
        """
        self.logger.info("Stopping Copy Trading Bot...")
        self.running = False
