"""
kafka/producer.py — Synthetic e-commerce event generator for Kafka topics
Generates: orders-stream, inventory-updates, competitor-prices
Gracefully degrades if Kafka broker is unavailable (prints mock mode warning).
"""

import os
import sys
import json
import time
import uuid
import random
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

CATEGORIES = ["electronics", "apparel", "home", "books", "food"]
SEGMENTS = ["premium", "regular", "budget"]
COMPETITORS = ["Competitor_A", "Competitor_B", "Competitor_C"]
WAREHOUSES = ["warehouse_1", "warehouse_2", "warehouse_3"]

# Simulated price catalog for products (product_id → base_price)
PRODUCT_CATALOG = {pid: random.uniform(200, 25000) for pid in range(1, 1001)}
PRODUCT_CATEGORIES = {pid: random.choice(CATEGORIES) for pid in range(1, 1001)}


def _epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def generate_order_event() -> dict:
    product_id = random.randint(1, 1000)
    base_price = PRODUCT_CATALOG[product_id]
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": _epoch_ms(),
        "product_id": product_id,
        "quantity": random.randint(1, 20),
        "order_value": round(base_price * random.uniform(0.8, 1.2), 2),
        "customer_segment": random.choice(SEGMENTS),
        "category": PRODUCT_CATEGORIES[product_id],
    }


def generate_inventory_event() -> dict:
    product_id = random.randint(1, 1000)
    change = random.choice([-1, -1, -2, -5, -10, +100, +500])  # mostly sales, occasional restock
    new_level = max(0, random.randint(0, 10000) + change)
    return {
        "timestamp": _epoch_ms(),
        "product_id": product_id,
        "warehouse": random.choice(WAREHOUSES),
        "new_level": new_level,
        "change": change,
        "event_type": "restock" if change > 0 else "sale",
    }


def generate_competitor_event() -> dict:
    product_id = random.randint(1, 1000)
    base_price = PRODUCT_CATALOG[product_id]
    previous_price = base_price * random.uniform(0.85, 1.15)
    price = previous_price * random.uniform(0.90, 1.10)
    return {
        "timestamp": _epoch_ms(),
        "product_id": product_id,
        "competitor_name": random.choice(COMPETITORS),
        "price": round(price, 2),
        "previous_price": round(previous_price, 2),
        "change_pct": round((price - previous_price) / previous_price * 100, 2),
    }


def run_mock_mode(duration_seconds: int = 30):
    """Run in mock mode (no Kafka) — just prints generated events."""
    logger.warning("MOCK MODE — Kafka unavailable. Simulating 10 events then stopping.")
    for i in range(10):
        order = generate_order_event()
        logger.info("Mock order event: product_id=%d value=%.2f", order["product_id"], order["order_value"])
        time.sleep(0.1)
    logger.info("Mock mode complete. To use real Kafka, start broker on %s", BOOTSTRAP_SERVERS)


def run_kafka_producer(rate_per_sec: int = 10, duration_seconds: int = 300):
    """Produce events to Kafka topics at the specified rate."""
    try:
        from confluent_kafka import Producer, KafkaException

        def delivery_callback(err, msg):
            if err:
                logger.error("Delivery failed for %s: %s", msg.topic(), err)

        conf = {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "socket.timeout.ms": 5000,
        }
        producer = Producer(conf)
        logger.info("Kafka producer connected to %s", BOOTSTRAP_SERVERS)
        logger.info("Producing %d events/sec for %ds…", rate_per_sec, duration_seconds)

        start = time.time()
        event_count = 0

        while time.time() - start < duration_seconds:
            cycle_start = time.time()

            # 10 orders per cycle
            for _ in range(rate_per_sec):
                evt = generate_order_event()
                producer.produce(
                    "orders-stream",
                    key=str(evt["product_id"]).encode(),
                    value=json.dumps(evt).encode(),
                    callback=delivery_callback,
                )
                event_count += 1

            # 2 inventory updates per cycle
            for _ in range(2):
                evt = generate_inventory_event()
                producer.produce(
                    "inventory-updates",
                    key=str(evt["product_id"]).encode(),
                    value=json.dumps(evt).encode(),
                    callback=delivery_callback,
                )
                event_count += 1

            # 1 competitor price per cycle
            evt = generate_competitor_event()
            producer.produce(
                "competitor-prices",
                key=str(evt["product_id"]).encode(),
                value=json.dumps(evt).encode(),
                callback=delivery_callback,
            )
            event_count += 1

            producer.poll(0)  # Non-blocking poll for delivery callbacks

            # Maintain rate
            elapsed = time.time() - cycle_start
            sleep_time = max(0, 1.0 - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

            if event_count % 100 == 0:
                logger.info("Produced %d events (%.0fs elapsed)…", event_count, time.time() - start)

        producer.flush(timeout=10)
        logger.info("Producer done. Total events: %d", event_count)

    except ImportError:
        logger.warning("confluent_kafka not installed. Running in mock mode.")
        run_mock_mode()
    except Exception as e:
        logger.warning("Kafka unavailable (%s). Running in mock mode.", e)
        run_mock_mode()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pricing Event Producer")
    parser.add_argument("--rate", type=int, default=10, help="Events/second")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds")
    args = parser.parse_args()
    run_kafka_producer(args.rate, args.duration)
