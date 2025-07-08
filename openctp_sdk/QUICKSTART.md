# OpenCTP SDK Quick Start Guide

快速开始使用 OpenCTP SDK - 一个易用、可复用的行情和交易网关 SDK

## 安装

1. 安装 OpenCTP-CTP:
```bash
pip install openctp-ctp==6.7.2.* -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host=pypi.tuna.tsinghua.edu.cn
```

2. 将 `openctp_sdk` 目录复制到您的项目中

## 5分钟快速体验

### 1. 行情网关 - 获取实时行情数据

```python
from openctp_sdk import MarketDataGateway, MarketData

def on_market_data(data: MarketData):
    print(f"{data.instrument_id}: 最新价={data.last_price}, 买一价={data.bid_price1}, 卖一价={data.ask_price1}")

# 创建行情网关
gateway = MarketDataGateway("tcp://180.168.146.187:10131")
gateway.set_market_data_callback(on_market_data)

# 连接并订阅
gateway.connect()
gateway.subscribe(["au2406", "ag2406"])  # 订阅黄金和白银

print("正在接收行情数据，按 Enter 退出...")
input()
gateway.disconnect()
```

### 2. 交易网关 - 下单和查询

```python
from openctp_sdk import TradingGateway, Direction, Offset

# 创建交易网关 (使用 SimNow 模拟账户)
gateway = TradingGateway(
    front_address="tcp://180.168.146.187:10130",
    broker_id="9999",
    user_id="您的用户名",      # 替换为您的 SimNow 用户名
    password="您的密码",       # 替换为您的密码
    app_id="simnow_client_test",
    auth_code="0000000000000000"
)

# 连接 (包含认证和登录)
gateway.connect()

# 查询账户资金
account = gateway.query_account()
print(f"可用资金: {account.available:.2f}")

# 查询持仓
positions = gateway.query_positions()
print(f"持仓数量: {len(positions)}")

# 下单 (示例 - 使用安全价格避免意外成交)
order_ref = gateway.place_order(
    instrument_id="au2406",    # 黄金
    direction=Direction.BUY,   # 买入
    offset=Offset.OPEN,        # 开仓
    price=400.0,               # 安全低价
    volume=1                   # 1手
)

print(f"订单已提交: {order_ref}")

# 撤单
gateway.cancel_order(order_ref)
gateway.disconnect()
```

### 3. 完整交易机器人

```python
from openctp_sdk import MarketDataGateway, TradingGateway, MarketData, OrderInfo
from openctp_sdk.common import Direction, Offset, setup_logger

class SimpleBot:
    def __init__(self):
        self.logger = setup_logger("TradingBot")
        
        # 创建网关
        self.md_gateway = MarketDataGateway("tcp://180.168.146.187:10131")
        self.td_gateway = TradingGateway(
            front_address="tcp://180.168.146.187:10130",
            broker_id="9999",
            user_id="您的用户名",
            password="您的密码", 
            app_id="simnow_client_test",
            auth_code="0000000000000000"
        )
        
        # 设置回调
        self.md_gateway.set_market_data_callback(self.on_market_data)
        self.td_gateway.set_order_callback(self.on_order_update)
    
    def on_market_data(self, data: MarketData):
        self.logger.info(f"行情更新: {data.instrument_id} = {data.last_price}")
        
        # 简单交易逻辑 (仅示例)
        if data.instrument_id == "au2406" and data.last_price > 0:
            # 在这里实现您的交易策略
            pass
    
    def on_order_update(self, order: OrderInfo):
        self.logger.info(f"订单更新: {order.instrument_id} - {order.order_status}")
    
    def start(self):
        # 连接
        self.md_gateway.connect()
        self.td_gateway.connect()
        
        # 订阅行情
        self.md_gateway.subscribe(["au2406", "ag2406"])
        
        self.logger.info("交易机器人已启动")
        
        # 保持运行
        try:
            input("按 Enter 停止...")
        finally:
            self.stop()
    
    def stop(self):
        self.md_gateway.disconnect()
        self.td_gateway.disconnect()
        self.logger.info("交易机器人已停止")

# 运行机器人
if __name__ == "__main__":
    bot = SimpleBot()
    bot.start()
```

## 核心特性

### 🚀 简单易用
- **直观的 API**: 隐藏 CTP 复杂性，提供简洁接口
- **自动重连**: 网络断开自动重连，无需手动处理
- **错误处理**: 完善的异常处理和错误提示
- **类型提示**: 完整的类型注解，IDE 智能提示

### 📊 行情网关 (MarketDataGateway)
```python
# 基本用法
gateway = MarketDataGateway("服务器地址")
gateway.set_market_data_callback(your_callback)
gateway.connect()
gateway.subscribe(["合约列表"])

# 高级功能
gateway.set_connection_callback(on_connected)
gateway.set_error_callback(on_error)
gateway.unsubscribe(["合约列表"])
is_connected = gateway.is_connected()
```

### 💼 交易网关 (TradingGateway)
```python
# 基本用法
gateway = TradingGateway(服务器, 经纪商, 用户名, 密码, ...)
gateway.connect()  # 自动完成认证、登录、结算确认

# 交易操作
order_ref = gateway.place_order(合约, 方向, 开平, 价格, 数量)
gateway.cancel_order(order_ref)

# 查询操作
account = gateway.query_account()
positions = gateway.query_positions()
orders = gateway.query_orders()

# 实时回调
gateway.set_order_callback(on_order_update)
gateway.set_position_callback(on_position_update)
```

### 🛡️ 数据结构
```python
# 行情数据
class MarketData:
    instrument_id: str      # 合约代码
    last_price: float       # 最新价
    bid_price1: float       # 买一价
    ask_price1: float       # 卖一价
    volume: int             # 成交量
    # ... 更多字段

# 订单信息
class OrderInfo:
    order_ref: str          # 订单引用
    instrument_id: str      # 合约代码
    direction: str          # 买卖方向
    order_status: str       # 订单状态
    limit_price: float      # 委托价格
    # ... 更多字段
```

## 配置文件

创建 `config.json` 配置文件:

```json
{
  "market_data": {
    "front_address": "tcp://180.168.146.187:10131",
    "instruments": ["au2406", "ag2406", "cu2406"]
  },
  "trading": {
    "front_address": "tcp://180.168.146.187:10130",
    "broker_id": "9999",
    "user_id": "您的用户名",
    "password": "您的密码",
    "app_id": "simnow_client_test", 
    "auth_code": "0000000000000000"
  }
}
```

使用配置文件:
```python
from openctp_sdk.common import load_config

config = load_config("config.json")
gateway = TradingGateway(**config["trading"])
```

## 常用操作

### 订单管理
```python
from openctp_sdk.common import Direction, Offset, PriceType

# 买入开仓
order_ref = gateway.place_order(
    instrument_id="au2406",
    direction=Direction.BUY,
    offset=Offset.OPEN,
    price=500.0,
    volume=1,
    price_type=PriceType.LIMIT_PRICE
)

# 卖出平仓
order_ref = gateway.place_order(
    instrument_id="au2406", 
    direction=Direction.SELL,
    offset=Offset.CLOSE,
    price=505.0,
    volume=1
)

# 撤单
gateway.cancel_order(order_ref)
```

### 查询操作
```python
# 查询账户
account = gateway.query_account()
print(f"可用资金: {account.available}")
print(f"总资产: {account.balance}")

# 查询持仓
positions = gateway.query_positions()
for pos in positions:
    if pos.position > 0:
        print(f"{pos.instrument_id}: {pos.position} 手")

# 查询订单
orders = gateway.query_orders()
for order in orders:
    print(f"{order.instrument_id}: {order.order_status}")
```

### 错误处理
```python
from openctp_sdk.common import OpenCTPError, ConnectionError, TradingError

try:
    gateway.connect()
except ConnectionError as e:
    print(f"连接失败: {e}")
except TradingError as e:
    print(f"交易错误: {e}")
except OpenCTPError as e:
    print(f"SDK 错误: {e}")
```

## 最佳实践

### 1. 连接管理
```python
try:
    gateway.connect()
    # 您的交易逻辑
finally:
    gateway.disconnect()  # 确保断开连接
```

### 2. 回调函数
```python
def on_market_data(data):
    # 保持处理简单快速
    # 避免在回调中进行耗时操作
    pass

def on_order_update(order):
    # 使用日志而非 print
    logger.info(f"订单更新: {order.order_ref}")
```

### 3. 线程安全
```python
import threading
import queue

# 使用队列处理数据
data_queue = queue.Queue()

def on_market_data(data):
    data_queue.put(data)

def data_processor():
    while True:
        data = data_queue.get()
        # 处理数据
        process_data(data)

# 启动处理线程
threading.Thread(target=data_processor, daemon=True).start()
```

## 示例项目

查看 `examples/` 目录中的完整示例:

- `market_data_example.py` - 行情数据接收
- `trading_example.py` - 交易操作演示  
- `complete_example.py` - 完整交易机器人

## 注意事项

⚠️ **重要提醒**:
- 本 SDK 仅供学习和开发使用
- 实盘交易前请充分测试
- 实施适当的风险管理
- 遵守相关法规要求

💡 **开发建议**:
- 先在 SimNow 模拟环境测试
- 使用适当的日志记录
- 实现断线重连逻辑
- 定期备份重要数据

## 获取帮助

- 查看 `README.md` 获取详细文档
- 参考 `examples/` 中的示例代码
- 使用 `setup_logger` 启用调试日志