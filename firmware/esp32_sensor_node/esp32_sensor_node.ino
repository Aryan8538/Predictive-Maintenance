/*
 * ESP32 Sensor Node - AI-Based Predictive Maintenance System
 * Institution: Raj Kumar Goel Institute of Technology (RKGIT)
 * 
 * Hardware Connections:
 * - ADXL345 Accelerometer (I2C):
 *     VCC -> 3.3V
 *     GND -> GND
 *     SDA -> GPIO 21
 *     SCL -> GPIO 22
 * - DS18B20 Temperature Sensor (1-Wire):
 *     VCC -> 3.3V
 *     GND -> GND
 *     DATA -> GPIO 4 (10k pull-up resistor between DATA and 3.3V)
 *
 * MQTT Topics & 1Hz Telemetry:
 * - sensor/vibration:   {"x": float, "y": float, "z": float, "timestamp": int}
 * - sensor/temperature: {"temp": float, "timestamp": int}
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <sys/time.h>

// Include credentials from secrets.h if available
#if __has_include("secrets.h")
  #include "secrets.h"
#else
  #define WIFI_SSID     "YOUR_WIFI_SSID"
  #define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
  #define MQTT_BROKER   "192.168.1.100"
  #define MQTT_PORT     1883
  #define MQTT_CLIENT_ID "ESP32_PredictiveMaintenance_Node1"
  #define MQTT_USERNAME ""
  #define MQTT_PASSWORD ""
#endif

// Pin Definitions
#define PIN_ONE_WIRE_BUS 4
#define PIN_I2C_SDA      21
#define PIN_I2C_SCL      22

// Topics
const char* TOPIC_VIBRATION   = "sensor/vibration";
const char* TOPIC_TEMPERATURE = "sensor/temperature";

// Instances
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);
OneWire oneWire(PIN_ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Timing variables
unsigned long lastSampleTime = 0;
const unsigned long SAMPLE_INTERVAL_MS = 1000; // 1 Hz sampling
unsigned long lastMqttRetry = 0;
const unsigned long MQTT_RETRY_INTERVAL_MS = 5000;

// NTP Server for Epoch Milliseconds
const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec = 0;
const int   daylightOffset_sec = 0;

// Helper to get Unix Epoch Milliseconds
int64_t getEpochMillis() {
  struct timeval tv;
  gettimeofday(&tv, NULL);
  if (tv.tv_sec < 100000) {
    // If NTP not yet synced, fallback to millis() offset
    return (int64_t)1700000000000ULL + millis();
  }
  return ((int64_t)tv.tv_sec * 1000ULL) + (tv.tv_usec / 1000ULL);
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi connected. IP address: ");
    Serial.println(WiFi.localIP());
    configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  } else {
    Serial.println("\nWi-Fi connection timed out. Will retry in loop.");
  }
}

void connectMQTT() {
  if (mqttClient.connected()) return;
  if (WiFi.status() != WL_CONNECTED) return;

  unsigned long now = millis();
  if (now - lastMqttRetry > MQTT_RETRY_INTERVAL_MS) {
    lastMqttRetry = now;
    Serial.print("Connecting to MQTT broker: ");
    Serial.println(MQTT_BROKER);

    bool connected = false;
    if (strlen(MQTT_USERNAME) > 0) {
      connected = mqttClient.connect(MQTT_CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD);
    } else {
      connected = mqttClient.connect(MQTT_CLIENT_ID);
    }

    if (connected) {
      Serial.println("MQTT broker connected successfully.");
    } else {
      Serial.print("MQTT connect failed, rc=");
      Serial.println(mqttClient.state());
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=============================================");
  Serial.println("ESP32 Predictive Maintenance Sensor Node Initializing");
  Serial.println("=============================================");

  // Initialize I2C with specified pins
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

  // Initialize ADXL345
  if (!accel.begin()) {
    Serial.println("[ERROR] No ADXL345 detected! Check wiring.");
  } else {
    accel.setRange(ADXL345_RANGE_16_G);
    Serial.println("[OK] ADXL345 initialized (+/- 16g range).");
  }

  // Initialize DS18B20
  tempSensor.begin();
  int deviceCount = tempSensor.getDeviceCount();
  Serial.print("[OK] DS18B20 initialized. Sensors found: ");
  Serial.println(deviceCount);

  // Configure MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(512);

  // Connect to Wi-Fi
  connectWiFi();
}

void loop() {
  // Ensure network connectivity without blocking
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  if (!mqttClient.connected()) {
    connectMQTT();
  } else {
    mqttClient.loop();
  }

  // 1 Hz Sampling and Publishing Loop
  unsigned long currentMillis = millis();
  if (currentMillis - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = currentMillis;

    int64_t timestamp = getEpochMillis();

    // 1. Read ADXL345 Vibration (in g)
    sensors_event_t event;
    float ax = 0.0, ay = 0.0, az = 0.0;
    if (accel.getEvent(&event)) {
      // Adafruit sensor library returns m/s^2; convert to g by dividing by SENSORS_GRAVITY_EARTH (9.80665)
      ax = event.acceleration.x / SENSORS_GRAVITY_EARTH;
      ay = event.acceleration.y / SENSORS_GRAVITY_EARTH;
      az = event.acceleration.z / SENSORS_GRAVITY_EARTH;
    }

    // 2. Read DS18B20 Temperature
    tempSensor.requestTemperatures();
    float tempC = tempSensor.getTempCByIndex(0);
    if (tempC == DEVICE_DISCONNECTED_C) {
      Serial.println("[WARN] DS18B20 reading failed (disconnected).");
      tempC = 0.0;
    }

    // 3. Serialize and Publish Vibration Payload
    // Format: {"x": float, "y": float, "z": float, "timestamp": int}
    char vibPayload[128];
    snprintf(vibPayload, sizeof(vibPayload),
             "{\"x\":%.4f,\"y\":%.4f,\"z\":%.4f,\"timestamp\":%lld}",
             ax, ay, az, (long long)timestamp);

    // 4. Serialize and Publish Temperature Payload
    // Format: {"temp": float, "timestamp": int}
    char tempPayload[96];
    snprintf(tempPayload, sizeof(tempPayload),
             "{\"temp\":%.2f,\"timestamp\":%lld}",
             tempC, (long long)timestamp);

    // Print to Serial Console
    Serial.print("[VIB] ");
    Serial.println(vibPayload);
    Serial.print("[TMP] ");
    Serial.println(tempPayload);

    // Publish over MQTT if connected
    if (mqttClient.connected()) {
      mqttClient.publish(TOPIC_VIBRATION, vibPayload);
      mqttClient.publish(TOPIC_TEMPERATURE, tempPayload);
    }
  }
}
