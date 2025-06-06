# OpenCTP 期货行情网关 - 使用文档

## 1. 项目简介

本项目是一个基于 OpenCTP API 实现的期货行情网关。它旨在提供一个稳定、可扩展的解决方案，用于接收来自期货公司的实时行情数据，并通过 WebSocket 协议将这些数据转发给客户端应用程序。

主要功能：
*   连接到 CTP (Comprehensive Transaction Platform) 行情前置服务器。
*   支持订阅一个或多个期货合约的实时行情。
*   通过 WebSocket 为多个客户端提供实时行情数据流。
*   采用模块化设计，易于扩展和维护。
*   提供结构化的日志输出，方便监控和问题排查。

## 2. 系统架构

本行情网关主要由以下几个核心组件构成，它们通过内部队列进行异步通信，以实现高效的数据处理和转发：

*   **`main.py` (主应用模块)**:
    *   负责整个应用的启动、配置加载、以及各个核心组件的初始化和生命周期管理。
    *   设置并管理模块间的通信队列。
    *   处理操作系统的信号（如 `Ctrl+C`），以实现服务的优雅停机。

*   **`ctp_connector.py` (CTP连接器)**:
    *   **功能**: 专门负责与 CTP 行情前置服务器进行所有交互。
    *   **职责**:
        *   使用 OpenCTP Python API (thostmduserapi) 连接到指定的行情服务器。
        *   处理用户登录认证（如果 CTP 前置需要）。
        *   根据 `ClientInterface` 模块转发过来的指令，向 CTP 系统发起行情订阅 (`SubscribeMarketData`) 和取消订阅 (`UnSubscribeMarketData`) 请求。
        *   接收 CTP 前置推送的实时行情数据 (`OnRtnDepthMarketData`)。
        *   将原始行情数据进行初步格式化（例如，解码字节串，转换为字典结构），然后放入到专门的数据队列中，供 `DataProcessor` 消费。
        *   管理与 CTP 的连接状态，并在断线时尝试自动重连和重新订阅。

*   **`data_processor.py` (数据处理器)**:
    *   **功能**: 作为行情数据从 CTP 连接器到客户端接口的中间处理层。
    *   **职责**:
        *   从 `CTPConnector` 的输出数据队列中获取行情数据。
        *   **当前实现**: 目前该模块主要作为数据直通管道，未添加复杂的处理逻辑。收到的数据直接放入输出队列。
        *   **未来扩展**: 此模块预留了扩展能力，未来可以加入如数据清洗、格式转换、计算衍生指标（例如 VWAP、分钟线聚合）、数据校验或过滤等功能。
        *   将处理后的数据（目前是原始行情字典）放入到专门的数据队列中，供 `ClientInterface` 消费。

*   **`client_interface.py` (客户端接口)**:
    *   **功能**: 负责与下游的客户端应用程序进行 WebSocket 通信。
    *   **职责**:
        *   启动一个 WebSocket 服务器，监听指定的IP地址和端口。
        *   管理所有连接到网关的 WebSocket 客户端。
        *   接收客户端发送的 JSON 格式指令，主要包括：
            *   行情订阅请求 (例如: `{"action": "subscribe", "instrument_id": "au2406"}`)。
            *   取消行情订阅请求 (例如: `{"action": "unsubscribe", "instrument_id": "au2406"}`)。
        *   将解析后的订阅/取消订阅指令放入到命令队列中，供 `CTPConnector` 处理。
        *   从 `DataProcessor` 的输出数据队列中获取已处理的行情数据。
        *   根据客户端的订阅状态，将对应的行情数据实时、准确地广播给一个或多个已订阅该合约的客户端。
        *   处理客户端的连接建立和断开事件，并相应更新内部订阅状态。

**数据流转示意**:

```
外部客户端 <--> [ClientInterface (WebSocket)] <--> [DataProcessor (数据队列)] <--> [CTPConnector (CTP API)] <--> CTP行情前置
                                ^                                      |
                                |                                      |
                                +---- (命令队列，订阅/取消订阅) ----------+
```

## 3. 环境准备与安装

### 3.1. Python 版本
推荐使用 Python 3.7 或更高版本。

### 3.2. 依赖库安装
本项目主要依赖以下 Python 库：
*   `websockets`: 用于实现 WebSocket 服务器，提供客户端接口。

您可以使用 pip 来安装它：
```bash
pip install websockets
```

### 3.3. CTP API Python 封装
*   **获取API文件**: 本项目需要 CTP 官方提供的 Python API 封装文件。这通常包括 `thostmduserapi.so` (Linux) 或 `thostmduserapi.pyd` (Windows)，以及 `thosttraderapi.so`/`.pyd` (如果未来要支持交易) 和相关的结构体定义 Python 文件 (如 `thostmduserapi.py`)。这些文件需要从您的期货公司或者上期技术官网获取。
*   **版本对应**: 请确保您使用的 CTP API 版本与您期货公司主席系统要求的版本一致。项目中提供的 `6.x.x` 文件夹可能包含了一些版本的API，您可以根据实际情况选用或替换。
*   **放置API文件**:
    1.  **推荐做法**: 将获取到的 CTP API 相关文件（例如 `thostmduserapi.so` 和 `thostmduserapi.py`）放置到本项目的根目录下，或者一个统一的库文件夹内。
    2.  **PYTHONPATH**: 或者，可以将 CTP API 文件所在的目录添加到系统的 `PYTHONPATH` 环境变量中，以便 Python 解释器能够找到它们。

    例如，如果您的API文件在项目根目录下的 `ctp_api/linux64` 文件夹中，您可以这样设置 `PYTHONPATH` (Linux/macOS):
    ```bash
    export PYTHONPATH=$PYTHONPATH:/path/to/your/project/ctp_api/linux64
    ```
    或者在 Windows CMD 中:
    ```bash
    set PYTHONPATH=%PYTHONPATH%;C:\path\to\your\project\ctp_api\win64
    ```
    如果API文件直接放在项目根目录，通常 Python 可以直接找到。代码中 `import thostmduserapi` 会尝试加载这些模块。

### 3.4. (可选) 创建虚拟环境
为了保持项目依赖的隔离，推荐在 Python 虚拟环境中安装和运行本项目：
```bash
python -m venv venv
# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 在虚拟环境中安装依赖
pip install websockets
```

## 4. 配置说明

本行情网关通过环境变量进行主要参数的配置。您可以在启动网关前设置这些环境变量，或者通过 `.env` 文件（需配合 `python-dotenv` 库，但本项目默认未集成）等方式管理。

以下是主要的配置参数及其说明：

*   **`MD_FRONT_ADDRESS`**:
    *   描述: CTP 行情前置服务器的连接地址。
    *   格式: `tcp://<IP地址>:<端口>`
    *   默认值: `tcp://180.168.146.187:10131` (SimNow 7x24 测试环境行情前置)
    *   示例: `tcp://123.45.67.89:10131`

*   **`CTP_BROKER_ID`**:
    *   描述: 期货公司代码 (Broker ID)。
    *   默认值: `9999` (SimNow 测试环境)

*   **`CTP_USER_ID`**:
    *   描述: CTP 账户的投资者ID。对于 SimNow 行情服务，此字段通常不强制校验，可以留空或使用任意值。
    *   默认值: `""` (空字符串)

*   **`CTP_PASSWORD`**:
    *   描述: CTP 账户的密码。对于 SimNow 行情服务，此字段通常不强制校验。
    *   默认值: `""` (空字符串)

*   **`GATEWAY_WEBSOCKET_HOST`**:
    *   描述: 网关 WebSocket 服务器监听的 IP 地址。
    *   默认值: `0.0.0.0` (表示监听所有可用的网络接口)
    *   示例: `127.0.0.1` (仅本地访问)

*   **`GATEWAY_WEBSOCKET_PORT`**:
    *   描述: 网关 WebSocket 服务器监听的端口号。
    *   默认值: `8765`
    *   示例: `9000`

*   **`CTP_FLOW_PATH_ROOT`**:
    *   描述: CTP API 生成的日志和流水文件（flow 文件）的根目录。网关会在该目录下自动创建 `conn_flow/md/` 子目录来存放行情相关的 flow 文件。
    *   默认值: `.` (表示当前工作目录)
    *   示例: `/var/log/ctp_gateway_flow`

### 4.1. SimNow 测试环境配置示例

根据用户提供的 SimNow 仿真环境信息，您可以参考以下配置：

*   **BrokerID**: `9999`
*   **行情前置 (Market Front)**:
    *   电信线路1: `tcp://180.168.146.187:10211`
    *   电信线路2: `tcp://180.168.146.187:10212`
    *   (注意：SimNow 还区分交易前置，但本行情网关目前仅连接行情前置)
*   **AppID**: `simnow_client_test` (CTP Connector 中目前未直接使用 AppID 和 AuthCode 进行行情登录，CTP 行情API通常不需要这些)
*   **认证码 (AuthCode)**: `0000000000000000` (16个0)

因此，您可以这样设置环境变量 (以第一组电信线路为例):
```bash
export MD_FRONT_ADDRESS="tcp://180.168.146.187:10211"
export CTP_BROKER_ID="9999"
# CTP_USER_ID 和 CTP_PASSWORD 对于 SimNow 行情通常可以忽略或设为空
export CTP_USER_ID=""
export CTP_PASSWORD=""
export GATEWAY_WEBSOCKET_HOST="0.0.0.0"
export GATEWAY_WEBSOCKET_PORT="8765"
export CTP_FLOW_PATH_ROOT="./ctp_flow_data" # 自定义 flow 文件存放位置
```

## 5. 启动网关

完成环境准备和配置后，您可以直接运行 `main.py` 脚本来启动行情网关服务：

```bash
python main.py
```

启动后，您应该能看到类似以下的日志输出（具体格式和内容取决于日志级别设置）：
```
INFO:__main__:Starting Futures Market Data Gateway...
INFO:__main__:Configuration: MD_FRONT=tcp://180.168.146.187:10131, BROKER_ID=9999, WS_HOST=0.0.0.0, WS_PORT=8765, FLOW_ROOT=.
INFO:__main__:Initializing CTP Connector to tcp://180.168.146.187:10131...
INFO:ctp_connector:Created flow directory: ./conn_flow/md
INFO:ctp_connector:Using flow path: ./conn_flow/md
INFO:ctp_connector:Init called and command processor started.
INFO:__main__:Initializing Data Processor...
INFO:data_processor:Starting DataProcessor...
INFO:data_processor:Processing thread started.
INFO:data_processor:DataProcessor started.
INFO:__main__:Initializing Client Interface on 0.0.0.0:8765...
INFO:client_interface:Starting ClientInterface...
INFO:client_interface:WebSocket server started on ws://0.0.0.0:8765
INFO:client_interface:Data broadcaster thread started.
INFO:client_interface:ClientInterface server thread started.
INFO:__main__:Starting CTP Connector...
INFO:ctp_connector:Attempting login with ReqID: 1, UserID: , BrokerID: 9999
INFO:__main__:Starting Data Processor...
INFO:__main__:Starting Client Interface...
INFO:__main__:Gateway is now running. Press Ctrl+C to stop.
INFO:ctp_connector:Front connected.
INFO:ctp_connector:Login request sent successfully.
INFO:ctp_connector:Login successful. ReqID: 1, TradingDay: 20231020, UserID: YOUR_USER_ID_IF_RETURNED
INFO:ctp_connector:Resubscribing to 0 instruments: []
```

服务启动后会持续运行，接收和转发期货行情。按 `Ctrl+C` 可以优雅地关闭网关服务。

## 6. 客户端接入

行情网关通过 WebSocket 协议对外提供服务。客户端应用程序可以通过 WebSocket 连接到网关，发送订阅指令，并接收实时行情数据。

### 6.1. WebSocket 服务地址
*   地址格式: `ws://<GATEWAY_WEBSOCKET_HOST>:<GATEWAY_WEBSOCKET_PORT>`
*   例如，如果网关运行在本地，端口为 `8765`，则地址为: `ws://localhost:8765` 或 `ws://127.0.0.1:8765`。
*   如果 `GATEWAY_WEBSOCKET_HOST` 设置为 `0.0.0.0`，则可以使用服务器的实际IP地址从其他机器连接。

### 6.2. 通信协议 (JSON)
客户端与网关之间的通信采用 JSON 格式。

#### 6.2.1. 客户端 -> 网关 (指令)

*   **订阅行情 (Subscribe)**:
    ```json
    {
        "action": "subscribe",
        "instrument_id": "au2406"
    }
    ```
    *   `action`: 固定为 `"subscribe"`。
    *   `instrument_id`: 字符串，表示要订阅的期货合约代码。 (目前网关一次只处理一个合约ID的订阅指令。如需批量，客户端需多次发送)

*   **取消订阅行情 (Unsubscribe)**:
    ```json
    {
        "action": "unsubscribe",
        "instrument_id": "au2406"
    }
    ```
    *   `action`: 固定为 `"unsubscribe"`。
    *   `instrument_id`: 字符串，表示要取消订阅的期货合约代码。 (同上，一次一个)


#### 6.2.2. 网关 -> 客户端 (响应与数据)

*   **订阅/取消订阅状态响应**:
    网关在收到客户端的订阅或取消订阅请求后，会回复一个状态消息。
    *   成功订阅: `{"status": "subscribed", "instrument": "au2406"}`
    *   成功取消订阅: `{"status": "unsubscribed", "instrument": "au2406"}`
    *   发生错误: `{"status": "error", "message": "错误描述信息"}` (例如: `{"status": "error", "message": "Invalid JSON format."}`)

*   **实时行情数据 (Depth Market Data)**:
    订阅成功后，网关会向客户端推送该合约的实时行情数据。数据格式为 JSON 对象，字段与 CTP `CThostFtdcDepthMarketDataField` 结构体中的主要字段对应。示例如下：
    ```json
    {
        "InstrumentID": "au2406",
        "LastPrice": 450.12,
        "Volume": 15302,
        "UpdateTime": "10:30:01",
        "UpdateMillisec": 500,
        "BidPrice1": 450.10,
        "BidVolume1": 5,
        "AskPrice1": 450.14,
        "AskVolume1": 3,
        "OpenInterest": 78000.0,
        "TradingDay": "20231020",
        "ExchangeID": "SHFE",
        "OpenPrice": 448.00,
        "HighestPrice": 451.50,
        "LowestPrice": 447.80,
        "ClosePrice": 0.0,
        "SettlementPrice": 0.0,
        "PreClosePrice": 447.50,
        "PreSettlementPrice": 447.00,
        "PreOpenInterest": 77500.0,
        "UpperLimitPrice": 480.00,
        "LowerLimitPrice": 420.00,
        "AveragePrice": 449.80,
        "ActionDay": "20231020"
    }
    ```
    注意: `LastPrice`, `BidPrice1`, `AskPrice1` 等价格字段，以及 `ClosePrice`, `SettlementPrice`, `AveragePrice` 如果值为 CTP 返回的极大/极小值 (通常表示无效值)，网关会处理为 `0.0`。客户端应理解这些字段的业务含义。

### 6.3. 客户端示例 (Python - 使用 `websockets` 库)

```python
import asyncio
import websockets
import json
import time

async def client_example():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            # 订阅 au2406
            subscribe_cmd_1 = {"action": "subscribe", "instrument_id": "au2406"}
            print(f"Sending: {subscribe_cmd_1}")
            await websocket.send(json.dumps(subscribe_cmd_1))
            response = await websocket.recv()
            print(f"Subscription response 1: {response}")

            # 订阅 rb2410 (另一个例子)
            # subscribe_cmd_2 = {"action": "subscribe", "instrument_id": "rb2410"}
            # print(f"Sending: {subscribe_cmd_2}")
            # await websocket.send(json.dumps(subscribe_cmd_2))
            # response = await websocket.recv()
            # print(f"Subscription response 2: {response}")

            print("\nReceiving market data for 10 seconds...")
            start_time = time.time()
            while time.time() - start_time < 10:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    print(f"RX: {data['InstrumentID']} - Px: {data.get('LastPrice', 'N/A')} Vol: {data.get('Volume','N/A')} Ask1: {data.get('AskPrice1','N/A')} Bid1: {data.get('BidPrice1','N/A')}")
                except asyncio.TimeoutError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server.")
                    break
                except Exception as e:
                    print(f"Error processing message: {e}")
                    break

            # 取消订阅 au2406
            unsubscribe_cmd = {"action": "unsubscribe", "instrument_id": "au2406"}
            print(f"Sending: {unsubscribe_cmd}")
            await websocket.send(json.dumps(unsubscribe_cmd))
            response = await websocket.recv()
            print(f"Unsubscription response: {response}")

            print("\nReceiving data for 5 more seconds (au2406 should stop)...")
            start_time = time.time()
            while time.time() - start_time < 5:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    print(f"POST-UNSUB RX: {data['InstrumentID']} - Px: {data.get('LastPrice', 'N/A')}")
                except asyncio.TimeoutError:
                    pass
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server (post-unsub).")
                    break
            print("Client example finished.")

    except Exception as e:
        print(f"Error connecting or communicating: {e}")

if __name__ == "__main__":
    asyncio.run(client_example())
```

*(Note: The client example sends individual subscription requests. The server-side `client_interface.py` currently processes `instrument_id` as a single string. If batch subscription/unsubscription via a list in `instrument_id` is desired in a single client message, `_message_handler` in `client_interface.py` would need modification to iterate over the list and call `_handle_subscription` for each item. The current documentation reflects sending one instrument ID per command message.)*

## 7. 日志说明

行情网关在运行过程中会产生详细的日志，以帮助用户监控其运行状态和排查潜在问题。

### 7.1. 日志配置
*   **默认级别**: `INFO`。这意味着一般的信息、警告和错误都会被记录。如果需要更详细的调试信息（例如，每个命令的处理、每条行情的接收等），可以在 `main.py` 中修改 `logging.basicConfig` 的 `level` 参数为 `logging.DEBUG`。
*   **格式**: 日志的默认格式包含时间戳、日志记录器名称（通常是模块名）、日志级别以及具体的日志消息。
    ```
    YYYY-MM-DD HH:MM:SS - <logger_name> - <LEVELNAME> - <message>
    ```
    例如: `2023-10-20 10:00:05 - ctp_connector - INFO - Login successful. TradingDay: 20231020, UserID: testuser`
*   **输出**: 默认情况下，日志会输出到控制台（标准输出）。

### 7.2. 主要日志内容
*   **`main`**: 记录网关的启动、关闭、各组件的初始化过程以及配置信息。
*   **`ctp_connector`**:
    *   连接 CTP 前置的状态（连接成功、断开、原因）。
    *   登录 CTP 的请求和结果。
    *   订阅/取消订阅行情的请求发送情况及 CTP 的响应。
    *   接收到的行情数据（通常在 `DEBUG` 级别下详细记录，`INFO` 级别可能只记录概要或错误）。
    *   命令队列中命令的接收和处理。
*   **`data_processor`**:
    *   线程启动和停止。
    *   接收和发送数据的概要（通常在 `DEBUG` 级别）。
    *   队列满等警告信息。
*   **`client_interface`**:
    *   WebSocket 服务器的启动和停止。
    *   客户端的连接和断开事件。
    *   接收到的客户端指令（订阅/取消订阅）。
    *   向 CTP命令队列转发指令的情况。
    *   广播行情数据给客户端的概要（通常在 `DEBUG` 级别）。

### 7.3. 日志级别参考
*   `DEBUG`: 非常详细的诊断信息，通常用于开发和调试阶段。
*   `INFO`: 确认事情按预期运行的常规信息。
*   `WARNING`: 表明发生了一些意外情况，或者将来可能出现某些问题，但软件仍然按预期工作。
*   `ERROR`: 由于更严重的问题，软件的某些功能未能执行。
*   `CRITICAL`: 严重错误，表明程序本身可能无法继续运行。

用户可以根据日志输出快速定位网关运行中的问题，例如 CTP 连接失败、登录错误、订阅被拒、数据处理异常或客户端通信问题等。

## 8. 注意事项与未来展望

### 8.1. 当前状态与注意事项
*   **测试环境**: 本项目主要基于 SimNow 7x24 测试环境开发和调试。在生产环境中使用前，务必进行充分的测试和风险评估。
*   **CTP API版本**: 使用的 CTP API (`thostmduserapi`) 版本需要与期货公司主席系统兼容。请确保从官方渠道获取正确的API文件。
*   **错误处理**: 项目已包含基本的错误处理和日志记录，但仍有完善空间，例如更细致的重试机制、特定错误代码的针对性处理等。
*   **并发与性能**: 当前实现基于多线程和异步IO，适用于常见的行情订阅量。对于超大规模的并发客户端或海量合约订阅，可能需要进一步的性能分析和优化。
*   **安全性**: WebSocket 服务目前是明文 `ws://`。如果需要在公网环境部署，应考虑使用 `wss://` (WebSocket Secure) 并配置 SSL/TLS证书，同时增加认证授权机制。
*   **配置管理**: 目前配置主要通过环境变量。对于复杂部署，可以考虑引入配置文件 (如 YAML, TOML) 或配置中心。
*   **行情字段**: `OnRtnDepthMarketData` 推送的行情数据包含了大部分常用字段。如果需要其他特定字段，可能需要修改 `CTPConnector` 中数据拷贝和字典构建的部分。
*   **交易功能**: 本项目目前 **仅为行情网关**，不包含任何交易相关的功能。

### 8.2. 未来展望与可扩展方向
*   **完善的Web管理界面**: 开发一个简单的Web界面，用于监控网关状态、查看连接的客户端、动态调整订阅（尽管目前通过客户端指令可以实现）、管理日志级别等。
*   **数据持久化**: 将接收到的行情数据存储到数据库（如 InfluxDB, ClickHouse, PostgreSQL）或文件中，用于后续分析、回测或历史数据服务。
*   **指标计算与数据聚合**: 在 `DataProcessor` 中实现更复杂的行情处理逻辑，如计算K线、VWAP、布林带等技术指标，或按时间窗口聚合Tick数据。
*   **多种客户端协议支持**: 除了 WebSocket，未来可以考虑支持其他数据发布方式，如 ZeroMQ, gRPC, 或直接的 TCP Socket。
*   **交易网关集成**: 在当前行情网关的基础上，可以并行开发或集成一个交易网关模块，实现完整的程序化交易链路。
*   **更精细的订阅管理**: 例如，支持按交易所、按产品批量订阅；支持客户端查询当前已订阅列表等。
*   **热重载配置**: 支持在不重启服务的情况下，动态加载和更新部分配置。
*   **容器化部署**: 提供 Dockerfile 及相关编排文件 (如 Docker Compose, Kubernetes YAML)，简化部署和运维。
*   **增强安全性**: 实现客户端身份验证、API密钥、IP白名单等安全措施。

我们欢迎社区的贡献和建议，共同完善和发展这个项目。
