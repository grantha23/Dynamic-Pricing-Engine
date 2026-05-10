"""
kafka/consumer.py — Kafka consumer with 5-minute tumbling window aggregation
Publishes aggregated pricing signals to 'pricing-signals' topic.
Gracefully degrades to mock simulation if Kafka is unavailable.
"""

import os
import sys
import json
import time
import random
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kafka.pricing_trigger_rules import PricingRulesEngine

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CONSUMER_GROUP = "pricing-engine"
WINDOW_SIZE_SEC = 300   # 5-minute tumbling window
SLIDE_INTERVAL_SEC = 60  # Slide every 1 minute

# In-memory state stores
_order_windows: Dict[int, List[Dict]] = defaultdict(list)      # product_id → [order events]
_inventory_state: Dict[int, Dict] = {}                          # product_id → latest inventory
_competitor_state: Dict[int, List[Dict]] = defaultdict(list)    # product_id → [price events]
_our_prices: Dict[int, float] = {}                              # product_id → current price


def _epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _compute_window_metrics(product_id: int, window_start_ms: int) -> Dict[str, Any]:
    """Compute 5-minute window aggregation for a product."""
    now_ms = _epoch_ms()
    cutoff_ms = now_ms - (WINDOW_SIZE_SEC * 1000)

    # Filter orders within window
    orders_in_window = [
        e for e in _order_windows[product_id]
        if e.get("timestamp", 0) > cutoff_ms
    ]

    # Trim old orders
    _order_windows[product_id] = orders_in_window

    total_orders = len(orders_in_window)
    avg_order_value = (
        sum(e.get("order_value", 0) for e in orders_in_window) / total_orders
        if total_orders > 0 else 0.0
    )
    demand_rate = total_orders / (WINDOW_SIZE_SEC / 60.0)  # orders per minute

    # Inventory
    inv_data = _inventory_state.get(product_id, {})
    inventory_level = inv_data.get("new_level", random.randint(100, 9000))
    inventory_ratio = inventory_level / 10000.0

    # Competitor prices
    comp_events = _competitor_state.get(product_id, [])
    avg_competitor_price = (
        sum(e.get("price", 0) for e in comp_events[-5:]) / min(len(comp_events), 5)
        if comp_events else _our_prices.get(product_id, 1000.0) * 0.95
    )

    our_price = _our_prices.get(product_id, avg_competitor_price)
    price_gap_pct = (our_price - avg_competitor_price) / (avg_competitor_price + 1e-9) * 100

    # Demand trend (simple heuristic)
    if total_orders > 10:
        demand_trend = "increasing"
    elif total_orders < 2:
        demand_trend = "decreasing"
    else:
        demand_trend = "stable"

    urgency_score = min(1.0, (demand_rate / 10.0 + (1 - inventory_ratio)) / 2.0)

    return {
        "timestamp": now_ms,
        "product_id": product_id,
        "category": inv_data.get("category", "unknown"),
        "metrics": {
            "total_orders": total_orders,
            "avg_order_value": round(avg_order_value, 2),
            "demand_rate_orders_per_min": round(demand_rate, 3),
            "inventory_level": inventory_level,
            "inventory_ratio": round(inventory_ratio, 4),
            "avg_competitor_price": round(avg_competitor_price, 2),
            "our_current_price": round(our_price, 2),
            "price_gap_pct": round(price_gap_pct, 2),
            "demand_trend": demand_trend,
            "urgency_score": round(urgency_score, 4),
            "timestamp": now_ms,
        },
    }


def _process_message(topic: str, data: Dict[str, Any]):
    """Route incoming message to the appropriate state store."""
    product_id = data.get("product_id", 0)
    if not product_id:
        return

    if topic == "orders-stream":
        _order_windows[product_id].append(data)
        # Update our price cache from order_value
        if "order_value" not in _our_prices:
            _our_prices[product_id] = data.get("order_value", 1000.0)

    elif topic == "inventory-updates":
        _inventory_state[product_id] = data

    elif topic == "competitor-prices":
        _competitor_state[product_id].append(data)
        # Keep only last 10 competitor events per product
        _competitor_state[product_id] = _competitor_state[product_id][-10:]


def _publish_pricing_signals(signals: List[Dict], producer=None):
    """Publish computed pricing signals to Kafka or print in mock mode."""
    for signal in signals:
        if producer:
            try:
                producer.produce(
                    "pricing-signals",
                    key=str(signal["product_id"]).encode(),
                    value=json.dumps(signal).encode(),
                )
            except Exception as e:
                logger.error("Failed to publish signal for %d: %s", signal["product_id"], e)
        else:
            logger.info(
                "[SIGNAL] product=%d action=%s multiplier=%.2f urgency=%s",
                signal.get("product_id", 0),
                signal.get("action", "hold"),
                signal.get("multiplier", 1.0),
                signal.get("urgency", "low"),
            )


def run_mock_consumer(iterations: int = 5):
    """Simulate consumer without Kafka — generates mock events and applies rules."""
    logger.warning("MOCK CONSUMER MODE — Kafka unavailable.")
    rules_engine = PricingRulesEngine()

    CATEGORIES = ["electronics", "apparel", "home", "books", "food"]

    # Seed some state
    for pid in range(1, 51):
        for _ in range(random.randint(0, 20)):
            _order_windows[pid].append({
                "timestamp": _epoch_ms() - random.randint(0, 290000),
                "product_id": pid,
                "order_value": random.uniform(200, 5000),
                "customer_segment": random.choice(["premium", "regular", "budget"]),
                "category": random.choice(CATEGORIES),
            })
        _inventory_state[pid] = {
            "new_level": random.randint(0, 10000),
            "category": random.choice(CATEGORIES),
        }
        _our_prices[pid] = random.uniform(500, 20000)

    for i in range(iterations):
        logger.info("--- Window %d/%d ---", i + 1, iterations)
        active_products = list(_order_windows.keys()) or list(range(1, 11))
        signals = []
        for pid in active_products[:20]:
            metrics = _compute_window_metrics(pid, _epoch_ms())
            signal = rules_engine.evaluate(metrics)
            signals.append(signal)

        _publish_pricing_signals(signals)
        logger.info("Published %d pricing signals", len(signals))
        if i < iterations - 1:
            time.sleep(2)  # Shortened for demo

    logger.info("Mock consumer complete.")
    return signals


def run_kafka_consumer(duration_seconds: int = 300):
    """Consume events from Kafka topics and publish aggregated signals."""
    try:
        from confluent_kafka import Consumer, Producer, KafkaException, KafkaError

        consumer_conf = {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": CONSUMER_GROUP,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
            "socket.timeout.ms": 5000,
        }
        producer_conf = {"bootstrap.servers": BOOTSTRAP_SERVERS}

        consumer = Consumer(consumer_conf)
        producer = Producer(producer_conf)
        consumer.subscribe(["orders-stream", "inventory-updates", "competitor-prices"])

        rules_engine = PricingRulesEngine()
        last_window_time = time.time()
        msg_count = 0
        start = time.time()

        logger.info("Kafka consumer started — subscribed to 3 topics")

        while time.time() - start < duration_seconds:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                pass
            elif msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.error("Consumer error: %s", msg.error())
            else:
                try:
                    data = json.loads(msg.value().decode("utf-8"))
                    topic = msg.topic()
                    _process_message(topic, data)
                    msg_count += 1
                    consumer.commit(asynchronous=True)
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning("Skipping malformed message: %s", e)

            # Every SLIDE_INTERVAL_SEC, compute and publish signals
            now = time.time()
            if now - last_window_time >= SLIDE_INTERVAL_SEC:
                active_products = list(set(
                    list(_order_windows.keys()) +
                    list(_inventory_state.keys()) +
                    list(_competitor_state.keys())
                ))
                signals = []
                for pid in active_products:
                    metrics = _compute_window_metrics(pid, int(now * 1000))
                    signal = rules_engine.evaluate(metrics)
                    signals.append(signal)

                _publish_pricing_signals(signals, producer)
                producer.flush(timeout=5)
                logger.info(
                    "Window: %d messages | %d signals | %.0fs elapsed",
                    msg_count, len(signals), now - start,
                )
                last_window_time = now

        consumer.close()
        logger.info("Consumer stopped. Total messages: %d", msg_count)

    except ImportError:
        logger.warning("confluent_kafka not installed. Running in mock mode.")
        run_mock_consumer()
    except Exception as e:
        logger.warning("Kafka unavailable (%s). Running in mock mode.", e)
        run_mock_consumer()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pricing Event Consumer")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds")
    parser.add_argument("--mock", action="store_true", help="Force mock mode")
    args = parser.parse_args()

    if args.mock:
        run_mock_consumer()
    else:
        run_kafka_consumer(args.duration)
