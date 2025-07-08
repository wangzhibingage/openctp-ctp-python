# -*- coding: utf-8 -*-

"""
Common data types and structures for OpenCTP SDK
"""

from typing import Optional, Union, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import json

class Direction(Enum):
    """Order direction"""
    BUY = "0"
    SELL = "1"

class Offset(Enum):
    """Order offset"""
    OPEN = "0"      # 开仓
    CLOSE = "1"     # 平仓
    FORCE_CLOSE = "2"  # 强平
    CLOSE_TODAY = "3"  # 平今
    CLOSE_YESTERDAY = "4"  # 平昨
    FORCE_OFF = "5"  # 强减

class PriceType(Enum):
    """Order price type"""
    ANY_PRICE = "1"     # 任意价
    LIMIT_PRICE = "2"   # 限价
    BEST_PRICE = "3"    # 最优价
    LAST_PRICE = "4"    # 最新价

class OrderStatus(Enum):
    """Order status"""
    ALL_TRADED = "0"       # 全部成交
    PART_TRADED_QUEUEING = "1"  # 部分成交还在队列中
    PART_TRADED_NOT_QUEUEING = "2"  # 部分成交不在队列中
    NOT_TRADED_QUEUEING = "3"  # 未成交还在队列中
    NOT_TRADED_NOT_QUEUEING = "4"  # 未成交不在队列中
    CANCELED = "5"         # 撤单
    UNKNOWN = "a"          # 未知
    NOT_TOUCHED = "b"      # 尚未触发
    TOUCHED = "c"          # 已触发

@dataclass
class MarketData:
    """Market data structure"""
    instrument_id: str
    exchange_id: str
    last_price: float
    pre_settlement_price: float
    pre_close_price: float
    pre_open_interest: float
    open_price: float
    highest_price: float
    lowest_price: float
    volume: int
    turnover: float
    open_interest: float
    close_price: float
    settlement_price: float
    upper_limit_price: float
    lower_limit_price: float
    pre_delta: float
    curr_delta: float
    update_time: str
    update_millisec: int
    bid_price1: float
    bid_volume1: int
    ask_price1: float
    ask_volume1: int
    bid_price2: float = 0.0
    bid_volume2: int = 0
    ask_price2: float = 0.0
    ask_volume2: int = 0
    bid_price3: float = 0.0
    bid_volume3: int = 0
    ask_price3: float = 0.0
    ask_volume3: int = 0
    bid_price4: float = 0.0
    bid_volume4: int = 0
    ask_price4: float = 0.0
    ask_volume4: int = 0
    bid_price5: float = 0.0
    bid_volume5: int = 0
    ask_price5: float = 0.0
    ask_volume5: int = 0
    average_price: float = 0.0
    action_day: str = ""
    trading_day: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            field.name: getattr(self, field.name) 
            for field in self.__dataclass_fields__.values()
        }

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

@dataclass
class OrderInfo:
    """Order information structure"""
    broker_id: str
    investor_id: str
    order_ref: str
    user_id: str
    order_price_type: str
    direction: str
    combine_offset_flag: str
    combine_hedge_flag: str
    limit_price: float
    volume_total_original: int
    time_condition: str
    gtd_date: str
    volume_condition: str
    min_volume: int
    contingent_condition: str
    stop_price: float
    force_close_reason: str
    is_auto_suspend: int
    business_unit: str
    request_id: int
    order_local_id: str
    exchange_id: str
    participant_id: str
    client_id: str
    exchange_inst_id: str
    trader_id: str
    install_id: int
    order_submit_status: str
    notify_sequence: int
    trading_day: str
    settlement_id: int
    order_sys_id: str
    order_source: str
    order_status: str
    order_type: str
    volume_traded: int
    volume_total: int
    insert_date: str
    insert_time: str
    active_time: str
    suspend_time: str
    update_time: str
    cancel_time: str
    active_trader_id: str
    clearing_part_id: str
    sequence_no: int
    front_id: int
    session_id: int
    user_product_info: str
    status_msg: str
    user_force_close: int
    active_user_id: str
    broker_order_seq: int
    relative_order_sys_id: str
    zzce_confirm_id: int
    is_swap_order: int
    branch_id: str
    invest_unit_id: str
    account_id: str
    currency_id: str
    ip_address: str
    mac_address: str
    instrument_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            field.name: getattr(self, field.name) 
            for field in self.__dataclass_fields__.values()
        }

@dataclass
class PositionInfo:
    """Position information structure"""
    broker_id: str
    investor_id: str
    instrument_id: str
    position_direction: str
    hedge_flag: str
    position_date: str
    yd_position: int
    position: int
    long_frozen: int
    short_frozen: int
    long_frozen_amount: float
    short_frozen_amount: float
    open_volume: int
    close_volume: int
    open_amount: float
    close_amount: float
    position_cost: float
    pre_margin: float
    use_margin: float
    frozen_margin: float
    frozen_cash: float
    frozen_commission: float
    cash_in: float
    commission: float
    close_profit: float
    position_profit: float
    pre_settlement_price: float
    settlement_price: float
    trading_day: str
    settlement_id: int
    open_cost: float
    exchange_margin: float
    combine_position: int
    combine_long_frozen: int
    combine_short_frozen: int
    close_profit_by_date: float
    close_profit_by_trade: float
    today_position: int
    margin_rate_by_money: float
    margin_rate_by_volume: float
    strike_frozen: int
    strike_frozen_amount: float
    abandon_frozen: int
    exchange_id: str
    yd_strike_frozen: int
    invest_unit_id: str
    position_cost_offset: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            field.name: getattr(self, field.name) 
            for field in self.__dataclass_fields__.values()
        }

@dataclass
class AccountInfo:
    """Account information structure"""
    broker_id: str
    account_id: str
    pre_mortgage: float
    pre_credit: float
    pre_deposit: float
    pre_balance: float
    pre_margin: float
    interest_base: float
    interest: float
    deposit: float
    withdraw: float
    frozen_margin: float
    frozen_cash: float
    frozen_commission: float
    curr_margin: float
    cash_in: float
    commission: float
    close_profit: float
    position_profit: float
    balance: float
    available: float
    withdraw_quota: float
    reserve: float
    trading_day: str
    settlement_id: int
    credit: float
    mortgage: float
    exchange_margin: float
    delivery_margin: float
    exchange_delivery_margin: float
    reserve_balance: float
    currency_id: str
    pre_fund_mortgage_in: float
    pre_fund_mortgage_out: float
    fund_mortgage_in: float
    fund_mortgage_out: float
    fund_mortgage_available: float
    mortgage_able_fund: float
    spec_product_margin: float
    spec_product_frozen_margin: float
    spec_product_commission: float
    spec_product_frozen_commission: float
    spec_product_position_profit: float
    spec_product_close_profit: float
    spec_product_position_profit_by_algorithm: float
    spec_product_exchange_margin: float
    biz_type: str
    frozen_swap: float
    remain_swap: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            field.name: getattr(self, field.name) 
            for field in self.__dataclass_fields__.values()
        }

# Type aliases for callbacks
MarketDataCallback = Callable[[MarketData], None]
OrderCallback = Callable[[OrderInfo], None]
PositionCallback = Callable[[PositionInfo], None]
AccountCallback = Callable[[AccountInfo], None]
ErrorCallback = Callable[[str, int], None]
ConnectionCallback = Callable[[], None]
DisconnectionCallback = Callable[[int], None]