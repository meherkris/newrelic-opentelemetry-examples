package kafka;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;
import java.util.Random;
import java.util.logging.Logger;

public class ProducerApp {

    private static final Logger log = Logger.getLogger(ProducerApp.class.getName());

    private static final String[] PRODUCTS = {"laptop", "phone", "tablet", "headphones", "keyboard"};
    private static final String[] STATUSES = {"pending", "confirmed", "processing"};
    private static final String[] CARRIERS = {"fedex", "ups", "dhl", "usps"};
    private static final String[] METHODS  = {"credit_card", "debit_card", "paypal", "bank_transfer"};

    public static void main(String[] args) throws InterruptedException {
        String bootstrapServers = System.getenv().getOrDefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092");
        long intervalMs = Long.parseLong(System.getenv().getOrDefault("MESSAGE_INTERVAL_MS", "200"));

        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.RETRIES_CONFIG, 3);

        log.info("Starting Kafka Producer — bootstrap: " + bootstrapServers);

        Random rng = new Random();
        long count = 0;

        try (KafkaProducer<String, String> producer = new KafkaProducer<>(props)) {
            while (true) {
                producer.send(buildOrder(rng));
                producer.send(buildPayment(rng));
                producer.send(buildShipment(rng));
                count += 3;
                if (count % 300 == 0) {
                    log.info("Sent " + count + " messages total");
                }
                Thread.sleep(intervalMs);
            }
        }
    }

    static ProducerRecord<String, String> buildOrder(Random rng) {
        String orderId = "order-" + rng.nextInt(10_000);
        String product = PRODUCTS[rng.nextInt(PRODUCTS.length)];
        String status  = STATUSES[rng.nextInt(STATUSES.length)];
        double amount  = 10 + rng.nextDouble() * 990;
        int    qty     = 1 + rng.nextInt(5);
        String val = String.format(
            "{\"order_id\":\"%s\",\"product\":\"%s\",\"status\":\"%s\",\"amount\":%.2f,\"quantity\":%d,\"ts\":%d}",
            orderId, product, status, amount, qty, System.currentTimeMillis());
        return new ProducerRecord<>("orders", orderId, val);
    }

    static ProducerRecord<String, String> buildPayment(Random rng) {
        String paymentId = "pay-" + rng.nextInt(10_000);
        String orderId   = "order-" + rng.nextInt(10_000);
        String method    = METHODS[rng.nextInt(METHODS.length)];
        double amount    = 10 + rng.nextDouble() * 990;
        String val = String.format(
            "{\"payment_id\":\"%s\",\"order_id\":\"%s\",\"method\":\"%s\",\"amount\":%.2f,\"ts\":%d}",
            paymentId, orderId, method, amount, System.currentTimeMillis());
        return new ProducerRecord<>("payments", paymentId, val);
    }

    static ProducerRecord<String, String> buildShipment(Random rng) {
        String shipmentId = "ship-" + rng.nextInt(10_000);
        String orderId    = "order-" + rng.nextInt(10_000);
        String carrier    = CARRIERS[rng.nextInt(CARRIERS.length)];
        String tracking   = carrier.toUpperCase() + rng.nextInt(1_000_000);
        String val = String.format(
            "{\"shipment_id\":\"%s\",\"order_id\":\"%s\",\"carrier\":\"%s\",\"tracking\":\"%s\",\"ts\":%d}",
            shipmentId, orderId, carrier, tracking, System.currentTimeMillis());
        return new ProducerRecord<>("shipments", shipmentId, val);
    }
}
