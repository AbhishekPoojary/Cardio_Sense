#include <driver/i2s.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <math.h>

// ==================== CONFIGURATION ====================
const char* WIFI_SSID     = "Nord5";
const char* WIFI_PASSWORD = "Abhishek1290";
const int   SERVER_PORT   = 8888;
const char* SERVER_HOST   = "10.116.198.147"; // Your Python Desktop IP

#define I2S_PORT       I2S_NUM_0
#define SAMPLE_RATE    16000

#define I2S_BCK        32
#define I2S_WS         25
#define I2S_SD_IN      33   // ICS-43434
#define I2S_SD_OUT     26   // MAX98357A DIN

#define BUTTON_PIN     4

// ==================== BUFFERS ==========================
int32_t mic_raw[64];
int16_t stereo_out[128];

// UDP Chunking Buffer (512 int16 samples = 1024 bytes, safe for UDP MTU)
#define SEND_BUF_SIZE 512
int16_t send_buffer[SEND_BUF_SIZE];
int send_buf_idx = 0;

// ==================== DSP Variables ====================
static float x_prev = 0;
static float hp_out = 0;
static float env_audio = 0;

// Biquad Filter Coefficients & States
float b0, b1, b2, a1, a2;
float bq_x1 = 0, bq_x2 = 0, bq_y1 = 0, bq_y2 = 0;

// ==================== BPM Variables ====================
unsigned long lastBeatTime = 0;
float bpm = 0;
bool beatLock = false;

// ==================== WiFi / UDP =======================
WiFiUDP udp;
bool streaming = false;
bool buttonPressed = false;
unsigned long streamStartTime = 0;
uint32_t totalSamplesStreamed = 0;

// ==================== FUNCTIONS ========================
void calculateBiquadLPF(float fc, float fs) {
  float w0 = 2.0 * PI * (fc / fs);
  float alpha = sin(w0) / (2.0 * 0.7071);
  float cosw0 = cos(w0);

  float a0 = 1.0 + alpha;
  b0 = ((1.0 - cosw0) / 2.0) / a0;
  b1 = (1.0 - cosw0) / a0;
  b2 = ((1.0 - cosw0) / 2.0) / a0;
  a1 = (-2.0 * cosw0) / a0;
  a2 = (1.0 - alpha) / a0;
}

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Calculate Biquad LPF (40 Hz cutoff for heartbeats)
  calculateBiquadLPF(40.0f, SAMPLE_RATE);

  // --- WiFi ---
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println("\nConnected! IP: " + WiFi.localIP().toString());

  // Start UDP and auto-stream
  udp.begin(SERVER_PORT);
  streaming = true;
  streamStartTime = millis();
  Serial.println("UDP streaming started automatically!");

  // --- I2S Setup ---
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_TX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 6,
    .dma_buf_len = 64,
    .use_apll = false,
    .tx_desc_auto_clear = true
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num   = I2S_BCK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_SD_OUT,
    .data_in_num  = I2S_SD_IN
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);

  Serial.println("UDP Stethoscope Streamer Ready!");
  Serial.println("Press button on GPIO4 or send 'S' to pause/resume.");
}

void loop() {
  // --- Button Toggle ---
  bool btnState = (digitalRead(BUTTON_PIN) == LOW);
  if (btnState && !buttonPressed) {
    buttonPressed = true;
    streaming = !streaming;
    if (streaming) streamStartTime = millis();
    Serial.println(streaming ? "UDP Streaming RESUMED" : "UDP Streaming PAUSED");
  }
  if (!btnState) buttonPressed = false;

  // --- Serial Toggle ---
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'S' || c == 's') {
      streaming = !streaming;
      if (streaming) streamStartTime = millis();
      Serial.println(streaming ? "UDP Streaming RESUMED" : "UDP Streaming PAUSED");
    }
  }

  // --- I2S Read & DSP ---
  size_t bytes_read, bytes_written;
  i2s_read(I2S_PORT, mic_raw, sizeof(mic_raw), &bytes_read, portMAX_DELAY);
  int samples = bytes_read / 4;

  for (int i = 0; i < samples; i++) {
    float raw = (float)(mic_raw[i] >> 14);

    // 1. High-Pass Filter (DC Blocking, ~10 Hz)
    hp_out = raw - x_prev + 0.995f * hp_out;
    x_prev = raw;

    // 2. Biquad Butterworth Low-Pass Filter (40 Hz)
    float bq_out = b0 * hp_out + b1 * bq_x1 + b2 * bq_x2 - a1 * bq_y1 - a2 * bq_y2;
    bq_x2 = bq_x1;
    bq_x1 = hp_out;
    bq_y2 = bq_y1;
    bq_y1 = bq_out;

    // 3. Make-up Gain
    float heart_signal = bq_out * 40.0f;

    // 4. Envelope & BPM Detection
    env_audio = 0.995f * env_audio + 0.005f * fabs(heart_signal);
    unsigned long now = millis();
    if (env_audio > 350.0f && !beatLock) {
      beatLock = true;
      if (lastBeatTime > 0) {
        unsigned long dt = now - lastBeatTime;
        if (dt > 400 && dt < 1500) {
          float newBpm = 60000.0f / dt;
          bpm = (bpm == 0) ? newBpm : (bpm * 0.8f + newBpm * 0.2f);
        }
      }
      lastBeatTime = now;
    }
    if (env_audio < 200.0f) beatLock = false;

    // 5. Hard Limiter
    float clean_audio = heart_signal;
    if (clean_audio > 15000.0f) clean_audio = 15000.0f;
    if (clean_audio < -15000.0f) clean_audio = -15000.0f;

    int16_t s = (int16_t)clean_audio;

    // Speaker output (stereo)
    stereo_out[i * 2]     = s;
    stereo_out[i * 2 + 1] = s;

    // --- UDP Buffering ---
    if (streaming) {
      send_buffer[send_buf_idx++] = s;
      if (send_buf_idx >= SEND_BUF_SIZE) {
        udp.beginPacket(SERVER_HOST, SERVER_PORT);
        udp.write((uint8_t*)send_buffer, SEND_BUF_SIZE * sizeof(int16_t));
        udp.endPacket();
        send_buf_idx = 0;
        totalSamplesStreamed += SEND_BUF_SIZE;
      }
    }
  }

  // --- I2S Speaker Write ---
  i2s_write(I2S_PORT, stereo_out, samples * 4, &bytes_written, portMAX_DELAY);

  // --- Status Output (1Hz) ---
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint > 1000) {
    lastPrint = millis();
    Serial.print("BPM: ");
    if (bpm > 0) Serial.print(bpm, 1);
    else Serial.print("--");

    if (streaming) {
      float secs = (millis() - streamStartTime) / 1000.0f;
      Serial.printf(" | UDP Streaming: %.1fs (%u samples)\n", secs, totalSamplesStreamed);
    } else {
      Serial.println(" | PAUSED");
    }
  }
}
